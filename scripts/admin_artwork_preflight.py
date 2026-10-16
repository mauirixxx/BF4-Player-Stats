"""Read-only BF4PS admin artwork deployment preflight. Prints no secrets."""
from pathlib import Path
import os
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
SITE = Path('/var/www/bf4playerstats.com')
SERVICE = Path('/etc/systemd/system/bf4ps-admin-api.service')
ENV = Path('/root/.config/bf4ps/admin-production.env')
checks = []

def check(name, condition, detail=''):
    checks.append((name, bool(condition), detail))

check('Development editor', (ROOT/'admin/artwork-editor.html').is_file())
check('Development admin console', (ROOT/'admin/console.html').is_file())
check('Development backend', (ROOT/'api/admin_console_api.py').is_file())
check('Artwork catalog', (SITE/'equipment-artwork.js').is_file())
check('Live admin API unit', SERVICE.is_file())
check('Admin service not running as root', SERVICE.is_file() and 'User=root' not in SERVICE.read_text())
check('Live private environment file', ENV.is_file())
if ENV.is_file():
    mode = stat.S_IMODE(ENV.stat().st_mode)
    check('Environment file is private', mode & 0o077 == 0)
    content = ENV.read_text()
    names = {line.split('=',1)[0] for line in content.splitlines() if '=' in line and not line.lstrip().startswith('#')}
    for name in ('BF4PS_ARTWORK_CATALOG','BF4PS_ARTWORK_PRIVATE','BF4PS_ARTWORK_PUBLIC'):
        check(name+' configured', name in names)
check('Public override directory', (SITE/'assets/equipment-overrides').is_dir())
check('Admin editor published', (SITE/'admin/artwork-editor.html').is_file())
check('Admin console published', (SITE/'admin/console.html').is_file())
for name, ok, detail in checks:
    print(('PASS' if ok else 'PENDING') + ': ' + name + ((' - '+detail) if detail else ''))
print('Summary: %d passed, %d pending' % (sum(x[1] for x in checks), sum(not x[1] for x in checks)))
sys.exit(0)
