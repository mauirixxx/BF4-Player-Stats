#!/usr/bin/env python3
"""Bounded, read-only-DB Battlelog platoon emblem cache reconciler."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from sqlalchemy import create_engine, text

DEFAULT_DIR = Path('/var/www/bf4playerstats.com/assets/platoon-emblems')
PATH = re.compile(r'/battlelog/prod/emblem/[0-9]+/[0-9]+/256/[0-9]+\.png')
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def emblem_asset(pid, template, directory):
    if not isinstance(template, str) or '[SIZE]' not in template or '[FORMAT]' not in template:
        return None
    url = template.replace('[SIZE]', '256').replace('[FORMAT]', 'png')
    parsed = urlsplit(url)
    # Legacy Battlelog records store http:// URLs; force TLS on the fixed allowlisted host.
    if parsed.scheme == 'http' and parsed.hostname == 'eaassets-a.akamaihd.net':
        url = 'https://' + url[len('http://'):]
        parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname != 'eaassets-a.akamaihd.net'
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or not PATH.fullmatch(parsed.path) or not re.fullmatch(r'[1-9][0-9]{0,18}', str(pid))):
        return None
    name = f'{pid}-{hashlib.sha256(url.encode()).hexdigest()[:16]}.png'
    return url, directory / name

def fetch(url, path):
    opener = build_opener(NoRedirect)
    req = Request(url, headers={'User-Agent': 'BF4PSPlatoonEmblemCache/1.0'})
    with opener.open(req, timeout=10) as response:
        if response.status != 200 or response.headers.get_content_type() != 'image/png':
            raise ValueError('Unexpected response')
        data = response.read(1_000_001)
    if not (len(data) <= 1_000_000 and data.startswith(PNG_MAGIC)):
        raise ValueError('Invalid or oversized PNG')
    temp = None
    try:
        fd, temp = tempfile.mkstemp(prefix='.emblem-', dir=path.parent)
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.chmod(temp, 0o644)
        os.replace(temp, path)
        temp = None
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)

def reconcile(engine, directory=DEFAULT_DIR, limit=20, cooldown=21600, dry_run=False):
    directory.mkdir(parents=True, exist_ok=True)
    checked = attempted = saved = failed = 0
    # Stream the small identity+emblem columns; never load rosters or large payloads.
    with engine.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        conn.execute(text("SET LOCAL statement_timeout='30000ms'"))
        rows = conn.execution_options(stream_results=True).execute(text(
            "SELECT platoon_id::text, emblem_path FROM platoons WHERE emblem_path IS NOT NULL ORDER BY platoon_id"))
        for pid, template in rows:
            checked += 1
            item = emblem_asset(pid, template, directory)
            if item is None:
                continue
            url, path = item
            if path.is_file():
                continue
            retry = path.with_suffix('.retry')
            if retry.exists() and time.time() - retry.stat().st_mtime < cooldown:
                continue
            if attempted >= limit:
                break
            attempted += 1
            if dry_run:
                print(f'Would fetch platoon {pid}', flush=True)
                continue
            try:
                fetch(url, path)
                retry.unlink(missing_ok=True)
                saved += 1
                print(f'Cached platoon {pid}', flush=True)
            except Exception as exc:
                failed += 1
                retry.touch()
                print(f'Emblem fetch failed platoon={pid} reason={type(exc).__name__}', flush=True)
    print(f'checked={checked} attempted={attempted} saved={saved} failed={failed}', flush=True)
    return failed

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--directory', type=Path, default=DEFAULT_DIR)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('limit must be between 1 and 100')
    engine = create_engine(os.environ['BF4PS_DATABASE_URL'], pool_pre_ping=True)
    reconcile(engine, args.directory, args.limit, dry_run=args.dry_run)

if __name__ == '__main__':
    main()
