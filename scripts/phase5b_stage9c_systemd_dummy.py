#!/usr/bin/env python3
"""Generate harmless Stage 9C systemd dependency test units; never install them.

Output is an operator-reviewed staging directory, not /etc/systemd/system.
No database, HTTP, collectors, or systemctl invocation.
"""
from __future__ import annotations

import argparse
from pathlib import Path

PREFIX = "bf4ps-stage9c-test"
GUARD = f"{PREFIX}-guard.service"
COLLECTOR = f"{PREFIX}-collector.service"
MATERIALIZER = f"{PREFIX}-materializer.service"


def render_units():
    guard = """[Unit]
Description=Stage 9C TEST ONLY dummy guard
[Service]
Type=exec
ExecStart=/usr/bin/sleep 3600
Restart=no
RuntimeMaxSec=90
KillMode=control-group
TimeoutStopSec=5
"""
    def dependent(kind):
        return f"""[Unit]
Description=Stage 9C TEST ONLY dummy {kind}
BindsTo={GUARD}
After={GUARD}
[Service]
Type=exec
ExecStart=/usr/bin/sleep 3600
Restart=no
RuntimeMaxSec=90
KillMode=control-group
TimeoutStopSec=5
"""
    return {GUARD: guard, COLLECTOR: dependent("collector"),
            MATERIALIZER: dependent("materializer")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("build/stage9c-systemd-dummy"))
    parser.add_argument("--write", action="store_true", help="Write harmless unit text to staging directory only")
    args = parser.parse_args()
    units = render_units()
    output = args.output_dir.resolve()
    if output == Path("/etc/systemd/system") or str(output).startswith("/etc/systemd/system/"):
        parser.error("REFUSING: systemd installation path")
    if not args.write:
        print(f"DRY RUN: would write {len(units)} dummy service files to {output}")
        for name in units:
            print(f"  {name}")
        return
    output.mkdir(parents=True, exist_ok=True)
    for name, data in units.items():
        target = output / name
        if target.is_symlink() or target.exists():
            parser.error(f"REFUSING: target already exists: {target}")
        target.write_text(data, encoding="utf-8")
        print(f"WROTE: {target}")
    print("No units installed or started. Review files and run systemd-analyze verify manually.")


if __name__ == "__main__":
    main()
