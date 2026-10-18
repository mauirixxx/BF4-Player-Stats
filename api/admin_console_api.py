"""Private BF4PS moderation HTTP API. Not mounted in Apache by default.

Requires BF4PS_ADMIN_PASSWORD_PBKDF2 (salt$hex digest), BF4PS_ADMIN_SESSION_SECRET,
BF4PS_ADMIN_ORIGIN, BF4PS_ADMIN_USER and a dedicated BF4PS_DATABASE_URL.
Never bind to a public interface; TLS is terminated at a restricted reverse proxy.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from collections import deque
from threading import Lock
from pathlib import Path
from base64 import urlsafe_b64encode, urlsafe_b64decode
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from sqlalchemy import create_engine, text
from admin_moderation_service import get_exclusion, set_exclusion, validate_identity
from artwork_store import ArtworkStore, allowed_keys, MAX_INPUT_BYTES

SESSION_SECONDS = 3600
MAX_BODY = 4096
engine = None
artwork_store = None
_login_failures = deque()
_login_lock = Lock()


def login_allowed(now=None):
    """Conservative process-wide lockout: 10 failed attempts per 15 minutes."""
    now = time.monotonic() if now is None else now
    with _login_lock:
        while _login_failures and now - _login_failures[0] >= 900:
            _login_failures.popleft()
        return len(_login_failures) < 10


def record_login_failure(now=None):
    now = time.monotonic() if now is None else now
    with _login_lock:
        _login_failures.append(now)



def config():
    keys = ('BF4PS_ADMIN_PASSWORD_FILE', 'BF4PS_ADMIN_SESSION_SECRET',
            'BF4PS_ADMIN_ORIGIN', 'BF4PS_ADMIN_USER', 'BF4PS_DATABASE_URL')
    values = {key: os.environ.get(key, '') for key in keys}
    if any(not value for value in values.values()):
        raise RuntimeError('Admin API disabled: missing required configuration')
    if len(values['BF4PS_ADMIN_SESSION_SECRET']) < 48:
        raise RuntimeError('Admin API session secret too short')
    if not values['BF4PS_ADMIN_ORIGIN'].startswith('https://'):
        raise RuntimeError('Admin API requires HTTPS origin')
    if not Path(values['BF4PS_ADMIN_PASSWORD_FILE']).is_absolute():
        raise RuntimeError('Admin password file must use an absolute path')
    return values


def password_hash(cfg):
    path = Path(cfg['BF4PS_ADMIN_PASSWORD_FILE'])
    if path.stat().st_mode & 0o077:
        raise RuntimeError('Admin password file must be private')
    return path.read_text().strip()


def hash_password(password):
    if not isinstance(password, str) or not 16 <= len(password) <= 128:
        raise ValueError('New password must be 16–128 characters')
    salt = secrets.token_hex(24)
    return salt + '$' + hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()


def change_password(cfg, current, replacement):
    old_hash = password_hash(cfg)
    if not isinstance(current, str) or not check_password(current, old_hash):
        raise ValueError('Incorrect current password')
    if check_password(replacement, old_hash):
        raise ValueError('Choose a different password')
    new_hash = hash_password(replacement)
    path = Path(cfg['BF4PS_ADMIN_PASSWORD_FILE'])
    temp = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(new_hash + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def effective_session_secret(cfg):
    return hmac.new(cfg['BF4PS_ADMIN_SESSION_SECRET'].encode(), password_hash(cfg).encode(), hashlib.sha256).hexdigest()


def b64(value):
    return urlsafe_b64encode(value).decode().rstrip('=')


def unb64(value):
    return urlsafe_b64decode(value + '=' * (-len(value) % 4))


def sign_session(user, secret, now=None):
    now = int(time.time() if now is None else now)
    payload = b64(json.dumps({'u': user, 't': now, 'n': secrets.token_hex(16)},
                             separators=(',', ':')).encode())
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + sig


def read_session(token, user, secret, now=None):
    try:
        payload, sig = token.split('.', 1)
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(unb64(payload))
        now = int(time.time() if now is None else now)
        if data['u'] != user or not isinstance(data['t'], int):
            return None
        if data['t'] > now or now - data['t'] >= SESSION_SECONDS:
            return None
        if not isinstance(data['n'], str) or len(data['n']) != 32:
            return None
        return data
    except (ValueError, TypeError, KeyError, UnicodeError):
        return None


def csrf_for(session, secret):
    return hmac.new(secret.encode(), ('csrf:' + session['n']).encode(), hashlib.sha256).hexdigest()


def check_password(password, stored):
    try:
        salt, expected = stored.split('$', 1)
        if len(salt) < 16 or len(expected) != 64:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, AttributeError, UnicodeError):
        return False


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload, cookie=None):
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store, private')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'")
        self.send_header('Content-Length', str(len(body)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
            token = jar['bf4ps_admin'].value
        except (KeyError, cookies.CookieError):
            return None
        cfg = config()
        return read_session(token, cfg['BF4PS_ADMIN_USER'], effective_session_secret(cfg))

    def require_session(self, csrf=False):
        session = self.session()
        if not session:
            self.reply(401, {'error': 'Administrator login required'})
            return None
        if csrf:
            cfg = config()
            expected = csrf_for(session, effective_session_secret(cfg))
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), expected):
                self.reply(403, {'error': 'CSRF verification failed'})
                return None
        return session

    def parse_body(self):
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= size <= MAX_BODY or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError()
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError()
            return body
        except (ValueError, UnicodeError):
            self.reply(400, {'error': 'Invalid JSON request'})
            return None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path not in ('/session', '/search', '/exclusions', '/audit', '/artwork/catalog', '/artwork/history', '/overview', '/database-info', '/queue/players', '/queue/platoons'):
            return self.reply(404, {'error': 'Not found'})
        session = self.require_session()
        if session is None:
            return
        cfg = config()
        if parsed.path == '/session':
            return self.reply(200, {'user': session['u'], 'csrf': csrf_for(session, effective_session_secret(cfg))})
        args = parse_qs(parsed.query)
        if parsed.path in ('/queue/players', '/queue/platoons'):
            with engine.connect() as conn:
                if parsed.path == '/queue/players':
                    records = conn.execute(text("""
                        SELECT j.job_id,j.resource,j.priority_class,j.priority_value,
                               j.status,j.eligible_at,j.started_at,s.soldier_id,s.current_name,s.platform
                        FROM collection_jobs j JOIN soldiers s ON s.soldier_id=j.soldier_id
                        WHERE j.status='running' OR (j.status='pending' AND j.eligible_at<=now())
                        ORDER BY CASE WHEN j.status='running' THEN 0 ELSE 1 END,
                          CASE WHEN j.status='running' THEN j.started_at END DESC NULLS LAST,
                          CASE WHEN j.status='pending' AND j.priority_class='interactive' THEN 0 ELSE 1 END,
                          j.priority_class ASC,j.priority_value DESC,j.eligible_at ASC,j.created_at ASC,j.job_id ASC
                        LIMIT 10
                    """)).mappings().all()
                else:
                    records = conn.execute(text("""
                        SELECT q.platoon_id,COALESCE(p.name,'New platoon') AS name,
                               p.tag,q.status,q.due AS next_refresh_at,p.last_success_at
                        FROM (
                            SELECT r.platoon_id,r.status,r.next_attempt_at AS due,
                              CASE WHEN r.status='running' THEN -1 ELSE 0 END AS priority
                            FROM platoon_requests r
                            WHERE r.status='running' OR
                              (r.status IN ('pending','failed') AND r.next_attempt_at<=now() AND r.attempts<8)
                            UNION ALL
                            SELECT p.platoon_id,'pending' AS status,
                              COALESCE(p.next_refresh_at,p.last_success_at+interval '1 day',now()) AS due,1 AS priority
                            FROM platoons p
                            WHERE COALESCE(p.next_refresh_at,p.last_success_at+interval '1 day',now())<=now()
                              AND NOT EXISTS(SELECT 1 FROM platoon_requests r WHERE r.platoon_id=p.platoon_id
                                AND r.status IN ('pending','failed','running'))
                        ) q LEFT JOIN platoons p ON p.platoon_id=q.platoon_id
                        ORDER BY q.priority,q.due,q.platoon_id LIMIT 10
                    """)).mappings().all()
            return self.reply(200, {'rows':[dict(r) for r in records], 'kind':parsed.path.rsplit('/',1)[-1], 'observed_at':time.time()})
        if parsed.path == '/database-info':
            try:
                with engine.connect() as conn:
                    conn.execute(text('SET TRANSACTION READ ONLY'))
                    conn.execute(text("SET LOCAL statement_timeout = '3000ms'"))
                    data = conn.execute(text("""
                        SELECT current_database() AS database_name,
                               pg_database_size(current_database()) AS size_bytes,
                               (SELECT version_num FROM public.alembic_version LIMIT 1) AS alembic_version,
                               d.xact_commit + d.xact_rollback AS transactions,
                               d.numbackends AS connections,
                               d.stats_reset AS stats_reset,
                               extract(epoch from clock_timestamp()) AS sampled_at
                        FROM pg_stat_database d WHERE d.datname = current_database()
                    """)).mappings().one()
                return self.reply(200, {**dict(data), 'sampled_at': float(data['sampled_at']), 'stats_reset': str(data['stats_reset']) if data['stats_reset'] else None})
            except Exception as exc:
                import logging
                logging.exception('Database health metrics failed')
                return self.reply(503, {'error': 'Database metrics temporarily unavailable'})
        if parsed.path == '/overview':
            try:
                summary_path = Path('/var/www/bf4playerstats.com/homepage-summary.json')
                platoons_path = Path('/var/www/bf4playerstats.com/platoons-data.json')
                summary = json.loads(summary_path.read_text())
                source = json.loads(platoons_path.read_text())
                platoons = source.get('platoons', [])
                tracked = set()
                supported = set()
                roster_accounts = 0
                for platoon in platoons:
                    roster_accounts += int(platoon.get('visible_member_count') or 0)
                    for member in platoon.get('members', []):
                        for persona in member.get('personas', []):
                            if persona.get('platform') in ('pc', 'playstation', 'xbox') and persona.get('soldier_id'):
                                supported.add(str(persona['soldier_id']))
                    tracked.update(str(k) for k in platoon.get('soldier_stats', {}))
                return self.reply(200, {'players': summary, 'platoons': {
                    'count': len(platoons), 'visible_roster_accounts': roster_accounts,
                    'unique_supported_soldiers': len(supported), 'unique_tracked_soldiers': len(tracked),
                    'updated': platoons_path.stat().st_mtime}})
            except (OSError, ValueError, TypeError, KeyError) as exc:
                return self.reply(503, {'error': 'Collection overview temporarily unavailable'})
        if parsed.path == '/artwork/catalog':
            return self.reply(200, {'keys': sorted(artwork_store.catalog), 'overrides': artwork_store.manifest()})
        if parsed.path == '/artwork/history':
            try:
                rows = artwork_store.history(args.get('kind', [''])[0], args.get('raw_key', [''])[0], args.get('role', [''])[0])
                return self.reply(200, {'rows': rows})
            except ValueError as exc:
                return self.reply(400, {'error': str(exc)})
        with engine.connect() as conn:
            if parsed.path == '/search':
                term = args.get('q', [''])[0].strip()
                if not 2 <= len(term) <= 80:
                    return self.reply(400, {'error': 'Search requires 2–80 characters'})
                rows = conn.execute(text("""
                    SELECT s.soldier_id,s.platform,s.persona_id,s.current_name,
                           COALESCE(e.active,false) AS excluded,e.reason_code
                    FROM public.soldiers s
                    LEFT JOIN public.player_exclusions e
                      ON e.platform=s.platform AND e.persona_id=s.persona_id
                    WHERE s.current_name ILIKE :q OR s.persona_id::text=:exact
                    ORDER BY s.soldier_id DESC LIMIT 30
                """), {'q': '%' + term.replace('%', '\\%').replace('_', '\\_') + '%',
                       'exact': term}).mappings().all()
            elif parsed.path == '/exclusions':
                rows = conn.execute(text("""
                    SELECT platform,persona_id,reason_code,created_by,created_at,updated_at
                    FROM public.player_exclusions WHERE active
                    ORDER BY updated_at DESC LIMIT 100
                """)).mappings().all()
            else:
                rows = conn.execute(text("""
                    SELECT audit_id,platform,persona_id,action,actor,reason_code,occurred_at
                    FROM public.player_exclusion_audit
                    ORDER BY audit_id DESC LIMIT 100
                """)).mappings().all()
        self.reply(200, {'rows': [dict(row) for row in rows]})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ('/login', '/logout', '/exclude', '/restore', '/change-password', '/artwork/publish', '/artwork/restore'):
            return self.reply(404, {'error': 'Not found'})
        cfg = config()
        if self.headers.get('Origin') != cfg['BF4PS_ADMIN_ORIGIN']:
            return self.reply(403, {'error': 'Origin verification failed'})
        if path != '/login' and self.require_session(csrf=True) is None:
            return
        if path == '/artwork/publish':
            return self.artwork_publish(cfg)
        body = self.parse_body()
        if body is None:
            return
        if path == '/artwork/restore':
            try:
                result = artwork_store.restore(body.get('kind'), body.get('raw_key'), body.get('role'), cfg['BF4PS_ADMIN_USER'])
                return self.reply(200, result)
            except ValueError as exc:
                return self.reply(400, {'error': str(exc)})
        if path == '/login':
            if not login_allowed():
                return self.reply(429, {'error': 'Too many failed login attempts; try again later'})
            if body.get('username') != cfg['BF4PS_ADMIN_USER']:
                record_login_failure()
                return self.reply(401, {'error': 'Invalid credentials'})
            password = body.get('password', '')
            if not isinstance(password, str) or len(password) > 512 or not check_password(password, password_hash(cfg)):
                record_login_failure()
                time.sleep(0.3)
                return self.reply(401, {'error': 'Invalid credentials'})
            token = sign_session(cfg['BF4PS_ADMIN_USER'], effective_session_secret(cfg))
            cookie = 'bf4ps_admin=' + token + '; Path=/bf4ps-admin-api/; Max-Age=3600; Secure; HttpOnly; SameSite=Strict'
            return self.reply(200, {'ok': True}, cookie)
        if path == '/change-password':
            try:
                change_password(cfg, body.get('current_password'), body.get('new_password'))
            except (ValueError, TypeError) as exc:
                return self.reply(400, {'error': str(exc)})
            return self.reply(200, {'ok': True, 'login_required': True},
                              'bf4ps_admin=; Path=/bf4ps-admin-api/; Max-Age=0; Secure; HttpOnly; SameSite=Strict')
        if path == '/logout':
            return self.reply(200, {'ok': True},
                              'bf4ps_admin=; Path=/bf4ps-admin-api/; Max-Age=0; Secure; HttpOnly; SameSite=Strict')
        try:
            platform = body['platform']
            persona_id = body['persona_id']
            validate_identity(platform, persona_id)
            reason = body['reason_code']
            note = body.get('private_note')
            with engine.begin() as conn:
                result = set_exclusion(conn, platform=platform, persona_id=persona_id,
                                       active=(path == '/exclude'), actor=cfg['BF4PS_ADMIN_USER'],
                                       reason_code=reason, private_note=note)
            return self.reply(200, result)
        except (ValueError, KeyError):
            return self.reply(400, {'error': 'Invalid moderation request'})

    def artwork_publish(self, cfg):
        """Binary image upload. Identity is supplied via query parameters."""
        parsed = urlparse(self.path)
        args = parse_qs(parsed.query)
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if self.headers.get('Content-Type', '').split(';')[0] not in ('image/png', 'image/jpeg', 'image/webp'):
                raise ValueError('Unsupported image content type')
            if not 0 < length <= MAX_INPUT_BYTES:
                raise ValueError('Image upload exceeds size limit')
            kind = args.get('kind', [''])[0]
            raw_key = args.get('raw_key', [''])[0]
            role = args.get('role', [''])[0]
            from artwork_store import verify_catalog
            verify_catalog(kind, raw_key, role, artwork_store.catalog)
            image = self.rfile.read(length)
            if len(image) != length:
                raise ValueError('Incomplete image upload')
            result = artwork_store.publish(kind, raw_key, role, image, cfg['BF4PS_ADMIN_USER'])
            return self.reply(200, result)
        except (ValueError, TypeError) as exc:
            return self.reply(400, {'error': str(exc)})

    def log_message(self, fmt, *args):
        # Do not log request bodies or cookie values.
        super().log_message(fmt, *args)


def main():
    global engine, artwork_store
    cfg = config()
    catalog_path = os.environ.get('BF4PS_ARTWORK_CATALOG', '')
    private_path = os.environ.get('BF4PS_ARTWORK_PRIVATE', '')
    public_path = os.environ.get('BF4PS_ARTWORK_PUBLIC', '')
    if not all((catalog_path, private_path, public_path)):
        raise RuntimeError('Artwork directories must be configured before starting admin API')
    artwork_store = ArtworkStore(private_path, public_path, allowed_keys(catalog_path, str(Path(catalog_path).with_name('equipment-names.js'))), catalog_path)
    engine = create_engine(cfg['BF4PS_DATABASE_URL'], pool_pre_ping=True, pool_size=2, max_overflow=0)
    # A loopback-only service; public access requires separately reviewed proxy authentication.
    server = ThreadingHTTPServer(('127.0.0.1', 8767), Handler)
    server.serve_forever()


if __name__ == '__main__':
    main()
