#!/usr/bin/env python3
"""Read-only local process check for unexpected BF4PS production materialization."""
from __future__ import annotations

import os
from pathlib import Path

MATERIALIZE_FLAG = "--materialize-production-jobs"
DISCOVERY_MARKERS = (
    "bf4ps.discovery_service",
    "bf4ps/discovery_service.py",
    "scripts/bf4ps_discovery",
)


def _cmdline(pid_dir: Path) -> str | None:
    try:
        raw = (pid_dir / "cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return None
    if not raw:
        return None
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()


def main() -> int:
    me = os.getpid()
    discoveries: list[tuple[int, str, bool]] = []
    for pid_dir in Path("/proc").iterdir():
        if not pid_dir.name.isdigit():
            continue
        pid = int(pid_dir.name)
        if pid == me:
            continue
        cmd = _cmdline(pid_dir)
        if not cmd or not any(marker in cmd for marker in DISCOVERY_MARKERS):
            continue
        discoveries.append((pid, cmd, MATERIALIZE_FLAG in cmd))

    materializing = [row for row in discoveries if row[2]]
    print("===== BF4PS STEP 9 EXTERNAL MATERIALIZATION PROCESS CHECK =====")
    print(f"discovery_processes={len(discoveries)} materializing_processes={len(materializing)}")
    for pid, cmd, enabled in discoveries:
        print(f"  PID={pid} materialization_enabled={enabled} cmd={cmd}")
    print("database writes: 0")
    print("Battlelog requests: 0")
    passed = not materializing
    print("BF4PS STEP 9 EXTERNAL MATERIALIZATION PROCESS CHECK: " + ("PASS" if passed else "FAIL"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
