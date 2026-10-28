#!/usr/bin/env python3
"""Atomic, lightweight social-preview index from the live platoon table."""
import json
import os
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, text
from cache_platoon_emblems import emblem_asset

ROOT = Path('/var/www/bf4playerstats.com')

def build(engine, root=ROOT):
    with engine.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        conn.execute(text("SET LOCAL statement_timeout='30000ms'"))
        rows = conn.execute(text('SELECT platoon_id::text AS id, name, tag, official_member_count, emblem_path FROM platoons'))
        index = {}
        for pid, name, tag, members, template in rows:
            emblem = emblem_asset(pid, template, root / 'assets/platoon-emblems')
            preview = root / 'assets/platoon-previews' / (emblem[1].stem + '-v2.png') if emblem else None
            local = ('/assets/platoon-previews/' + preview.name) if preview and preview.is_file() else ''
            index[pid] = {'name': name or '', 'tag': tag or '', 'members': members or 0, 'emblem': local}
    fd, tmp = tempfile.mkstemp(prefix='.platoon-preview-', dir=root)
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(index, file, ensure_ascii=False, separators=(',', ':'))
        os.chmod(tmp, 0o644)
        os.replace(tmp, root / 'platoon-preview-index.json')
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    print('indexed', len(index), 'platoons', flush=True)

if __name__ == '__main__':
    build(create_engine(os.environ['BF4PS_DATABASE_URL'], pool_pre_ping=True))
