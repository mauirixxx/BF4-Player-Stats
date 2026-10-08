#!/usr/bin/env python3
"""Stage 9C harmless transient-systemd dependency probe.

Creates ONLY sleep units with unique names. Never launches BF4PS, connects
to PostgreSQL, or sends Battlelog traffic. --execute is explicit.
"""
from __future__ import annotations

import argparse
import subprocess
import time
import uuid

def commands(prefix: str):
    guard = prefix + "-guard.service"
    worker = prefix + "-worker.service"
    create_guard = [
        "systemd-run", "--unit=" + guard, "--collect",
        "--property=RuntimeMaxSec=120", "/usr/bin/sleep", "100",
    ]
    create_worker = [
        "systemd-run", "--unit=" + worker, "--collect",
        "--property=BindsTo=" + guard,
        "--property=After=" + guard,
        "--property=RuntimeMaxSec=120", "/usr/bin/sleep", "100",
    ]
    return guard, worker, create_guard, create_worker

def run(cmd):
    return subprocess.run(cmd, text=True, capture_output=True, check=True, timeout=15)

def active(unit):
    result = subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=10)
    return result.returncode == 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Start harmless sleep units and exercise BindsTo")
    args = parser.parse_args()
    prefix = "bf4ps-stage9c-probe-" + uuid.uuid4().hex[:10]
    guard, worker, create_guard, create_worker = commands(prefix)
    print("GUARD:", " ".join(create_guard))
    print("WORKER:", " ".join(create_worker))
    if not args.execute:
        print("DRY RUN: no units created")
        return 0
    try:
        run(create_guard)
        run(create_worker)
        time.sleep(2)
        if not active(guard) or not active(worker):
            raise RuntimeError("both harmless units did not become active")
        print("PASS: both harmless units active")
        run(["systemctl", "stop", guard])
        deadline = time.monotonic() + 12
        while active(worker) and time.monotonic() < deadline:
            time.sleep(0.25)
        if active(worker):
            raise RuntimeError("FAIL: worker remained active after guard stop")
        print("PASS: BindsTo stopped harmless worker after guard stop")
        return 0
    finally:
        for unit in (worker, guard):
            subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=15)

if __name__ == "__main__":
    raise SystemExit(main())
