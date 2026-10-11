"""Launch a bounded local set of synthetic D2 soak workers and verify reports.

This process never provisions or cleans database rows and never makes HTTP.
The coordinator must stop every host before cleanup.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from scripts.phase5b_three_site_manifest import validate_manifest_document


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--duration-seconds", type=float, default=15)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args(argv)
    if not a.execute:
        p.error("--execute required")
    if not 1 <= a.duration_seconds <= 14400:
        p.error("invalid duration")
    manifest = validate_manifest_document(json.loads(a.manifest.read_text()))
    host = socket.gethostname().split(".")[0].lower()
    count = manifest.distribution.get(host, 0)
    if not count:
        p.error("host not in manifest")
    a.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    processes = []
    try:
        for index in range(count):
            prefix = a.output_dir / f"{host}-{index}"
            cmd = [
                sys.executable, "-m", "scripts.phase5b_three_site_soak_worker",
                "--manifest", str(a.manifest), "--state", str(a.state),
                "--worker-index", str(index),
                "--duration-seconds", str(a.duration_seconds),
                "--interval-seconds", "0.5", "--max-iterations", "100000",
                "--heartbeat", str(prefix) + ".jsonl",
                "--report", str(prefix) + ".json", "--execute",
            ]
            processes.append((index, subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)))
        reports = []
        for index, proc in processes:
            out, err = proc.communicate(timeout=a.duration_seconds + 45)
            if proc.returncode:
                raise RuntimeError(f"worker {index} failed ({proc.returncode}): {err[-500:]}")
            report = json.loads(out)
            if (report["status"] != "complete" or report["claims"] != report["releases"]
                    or report["lease_losses"] or report["http_requests"] or report["errors"]):
                raise RuntimeError(f"worker {index} unhealthy")
            reports.append(report)
        print(json.dumps({"host": host, "worker_count": count,
                          "claims": sum(r["claims"] for r in reports),
                          "releases": sum(r["releases"] for r in reports),
                          "http_requests": 0, "status": "PASS"}, sort_keys=True))
    finally:
        for _, proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for _, proc in processes:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


if __name__ == "__main__":
    main()
