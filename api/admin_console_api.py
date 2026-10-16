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
from base64 import urlsafe_b64encode, urlsafe_b64decode
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from sqlalchemy import create_engine, text
from admin_moderation_service import get_exclusion, set_exclusion, validate_identity

SESSION_SECONDS = 3600
MAX_BODY = 4096
engine = None
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
    keys = ('BF4PS_ADMIN_PASSWORD_PBKDF2', 'BF4PS_ADMIN_SESSION_SECRET',
            'BF4PS_ADMIN_ORIGIN', 'BF4PS_ADMIN_USER', 'BF4PS_DATABASE_URL')
    values = {key: os.environ.get(key, '') for key in keys}
    if any(not value for value in values.values()):
        raise RuntimeError('Admin API disabled: missing required configuration')
    if len(values['BF4PS_ADMIN_SESSION_SECRET']) < 48:
        raise RuntimeError('Admin API session secret too short')
    if not values['BF4PS_ADMIN_ORIGIN'].startswith('https://'):
        raise RuntimeError('Admin API requires HTTPS origin')
    return values


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
        return read_session(token, cfg['BF4PS_ADMIN_USER'], cfg['BF4PS_ADMIN_SESSION_SECRET'])

    def require_session(self, csrf=False):
        session = self.session()
        if not session:
            self.reply(401, {'error': 'Administrator login required'})
            return None
        if csrf:
            cfg = config()
            expected = csrf_for(session, cfg['BF4PS_ADMIN_SESSION_SECRET'])
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
        if parsed.path not in ('/session', '/search', '/exclusions', '/audit'):
            return self.reply(404, {'error': 'Not found'})
        session = self.require_session()
        if session is None:
            return
        cfg = config()
        if parsed.path == '/session':
            return self.reply(200, {'user': session['u'], 'csrf': csrf_for(session, cfg['BF4PS_ADMIN_SESSION_SECRET'])})
        args = parse_qs(parsed.query)
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
        if path not in ('/login', '/logout', '/exclude', '/restore'):
            return self.reply(404, {'error': 'Not found'})
        cfg = config()
        if self.headers.get('Origin') != cfg['BF4PS_ADMIN_ORIGIN']:
            return self.reply(403, {'error': 'Origin verification failed'})
        if path != '/login' and self.require_session(csrf=True) is None:
            return
        body = self.parse_body()
        if body is None:
            return
        if path == '/login':
            if not login_allowed():
                return self.reply(429, {'error': 'Too many failed login attempts; try again later'})
            password = body.get('password', '')
            if not isinstance(password, str) or len(password) > 512 or not check_password(password, cfg['BF4PS_ADMIN_PASSWORD_PBKDF2']):
                record_login_failure()
                time.sleep(0.3)
                return self.reply(401, {'error': 'Invalid credentials'})
            token = sign_session(cfg['BF4PS_ADMIN_USER'], cfg['BF4PS_ADMIN_SESSION_SECRET'])
            cookie = 'bf4ps_admin=' + token + '; Path=/bf4ps-admin-api/; Max-Age=3600; Secure; HttpOnly; SameSite=Strict'
            return self.reply(200, {'ok': True}, cookie)
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

    def log_message(self, fmt, *args):
        # Do not log request bodies or cookie values.
        super().log_message(fmt, *args)


def main():
    global engine
    cfg = config()
    engine = create_engine(cfg['BF4PS_DATABASE_URL'], pool_pre_ping=True, pool_size=2, max_overflow=0)
    # A loopback-only service; public access requires separately reviewed proxy authentication.
    server = ThreadingHTTPServer(('127.0.0.1', 8767), Handler)
    server.serve_forever()


if __name__ == '__main__':
    main()
