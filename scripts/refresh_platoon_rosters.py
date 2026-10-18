#!/usr/bin/env python3
"""Bounded, fail-closed refresh of explicitly configured official Battlelog rosters."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

IDS = {'wire': '754443074295858477', 'ucav': '4452867151931601735'}
MAX_BYTES = 2_000_000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state-dir', type=Path, default=Path('/var/lib/bf4ps-platoon'))
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    state = args.state_dir
    state.mkdir(parents=True, exist_ok=True)
    script_dir = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='bf4ps-refresh-') as temp:
        staged = []
        for i, (name, pid) in enumerate(IDS.items()):
            if i:
                time.sleep(10)
            url = f'https://battlelog.battlefield.com/bf4/platoons/members/{pid}/'
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; BF4PSPlatoonWatcher/1.0)', 'Accept': 'text/html'})
            try:
                with urllib.request.urlopen(request, timeout=35) as response:
                    if response.status != 200:
                        raise ValueError(f'HTTP {response.status}')
                    content = response.read(MAX_BYTES + 1)
                    if len(content) > MAX_BYTES:
                        raise ValueError('response too large')
                html = Path(temp) / (name + '.html')
                roster = Path(temp) / (name + '.json')
                html.write_bytes(content)
                proc = subprocess.run([sys.executable, str(script_dir / 'battlelog_platoon_roster.py'), str(html), '--output', str(roster)], capture_output=True, text=True, timeout=30)
                if proc.returncode:
                    raise ValueError('parser rejected response: ' + proc.stderr[-350:])
                doc = json.loads(roster.read_text())
                if str(doc['platoon']['platoon_id']) != pid or not doc['validation']['complete']:
                    raise ValueError('platoon ID or validation mismatch')
                print(f'{name}: verified {doc["validation"]["account_count"]} accounts, {doc["validation"]["bf4_platform_records"]} BF4 persona associations', flush=True)
                staged.append((name, html, roster))
            except (OSError, ValueError, urllib.error.URLError, subprocess.TimeoutExpired) as exc:
                print(f'{name}: refresh aborted; existing database and snapshots preserved: {exc}', file=sys.stderr)
                return 1
        if args.dry_run:
            print('Dry run: no database writes or snapshot replacements')
            return 0
        command = [sys.executable, str(script_dir / 'import_platoon_rosters.py'), *[str(roster) for _, _, roster in staged]]
        result = subprocess.run(command, text=True)
        if result.returncode:
            print('Database import failed; previous snapshots preserved', file=sys.stderr)
            return result.returncode
        for name, html, roster in staged:
            os.replace(html, state / f'{name}-members.html')
            os.replace(roster, state / f'{name}-roster.json')
        print('All platoons refreshed; snapshots replaced after database commit')
    return 0


if __name__ == '__main__':
    sys.exit(main())
