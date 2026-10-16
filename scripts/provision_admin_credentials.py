#!/usr/bin/env python3
"""One-time interactive BF4PS admin secret setup; run as root on tcou.

Never passes credentials on the command line or stores them in the Git repository.
"""
import getpass
import hashlib
import os
from pathlib import Path
import secrets
from urllib.parse import quote

from sqlalchemy import create_engine, text

ROOT = Path('/root/.config/bf4ps')
PASSWORD_FILE = ROOT / 'admin-password.hash'
ENV_FILE = ROOT / 'admin-production.env'
HOST = '192.168.10.78'
ROLE = 'bf4ps_admin_moderation'
DB = 'bf4_playerstats'

def private_write(path, contents):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(contents)
        output.flush()
        os.fsync(output.fileno())

def main():
    if os.geteuid() != 0:
        raise SystemExit('Run as root on tcou')
    if PASSWORD_FILE.exists() and PASSWORD_FILE.stat().st_size:
        raise SystemExit('Existing admin password hash detected; refusing to overwrite')
    if ENV_FILE.exists():
        raise SystemExit('Existing admin environment detected; refusing to overwrite')
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    db_password = getpass.getpass('Enter bf4ps_admin_moderation DATABASE password (not shown): ')
    if not db_password or '\n' in db_password:
        raise SystemExit('Invalid database password')
    url = f'postgresql+psycopg://{ROLE}:{quote(db_password, safe="")}@{HOST}:5432/{DB}'
    engine = create_engine(url, connect_args={'connect_timeout': 5})
    try:
        with engine.connect() as conn:
            who = conn.execute(text('SELECT current_user')).scalar_one()
            if who != ROLE:
                raise RuntimeError('Connected as unexpected role')
            conn.execute(text('SELECT COUNT(*) FROM public.player_exclusions')).scalar_one()
            conn.execute(text('SELECT COUNT(*) FROM public.player_exclusion_audit')).scalar_one()
            conn.execute(text('SELECT COUNT(*) FROM public.soldiers')).scalar_one()
    finally:
        engine.dispose()
    print('Database login and read access verified.')
    password = secrets.token_urlsafe(30)
    salt = secrets.token_hex(24)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    # An earlier interrupted setup may have created an empty file.
    if PASSWORD_FILE.exists():
        if PASSWORD_FILE.stat().st_size:
            raise SystemExit('Refusing to replace nonempty password file')
        PASSWORD_FILE.unlink()
    private_write(PASSWORD_FILE, salt + '$' + digest + '\n')
    secret = secrets.token_urlsafe(64)
    env = ('BF4PS_ADMIN_USER=mauirixxx\n'
           'BF4PS_ADMIN_ORIGIN=https://www.bf4playerstats.com\n'
           f'BF4PS_ADMIN_PASSWORD_FILE={PASSWORD_FILE}\n'
           f'BF4PS_ADMIN_SESSION_SECRET={secret}\n'
           f'BF4PS_DATABASE_URL={url}\n')
    private_write(ENV_FILE, env)
    print('\nADMIN USERNAME: mauirixxx')
    print('TEMPORARY WEBSITE PASSWORD:', password)
    print('Save the password now; it will not be shown again.')
    print('Credentials configured. Admin service has NOT been started.')

if __name__ == '__main__':
    main()
