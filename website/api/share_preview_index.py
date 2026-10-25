#!/usr/bin/env python3
"""Compact public metadata extracted from the existing platoon snapshot."""
import json, os, tempfile
from pathlib import Path
root=Path('/var/www/bf4playerstats.com')
source=root/'platoons-data.json'
target=root/'platoon-preview-index.json'
if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
    raise SystemExit(0)
with source.open() as f: data=json.load(f)
index={str(p['id']):{'name':p.get('name',''), 'tag':p.get('tag',''), 'members':p.get('official_member_count',0),'emblem':p.get('emblem_url','')} for p in data.get('platoons',[]) if p.get('id')}
fd,tmp=tempfile.mkstemp(prefix='.platoon-preview-',dir=root)
try:
    with os.fdopen(fd,'w') as f:
        json.dump(index,f,ensure_ascii=False,separators=(',',':'))
    os.chmod(tmp,0o644)
    os.replace(tmp,target)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print('indexed',len(index),'platoons')
