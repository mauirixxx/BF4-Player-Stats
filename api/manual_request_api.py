#!/usr/bin/env python3
"""Private, opt-in manual request API. Never reuses leaderboard credentials."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote
from sqlalchemy import create_engine, text

MAX_BODY = 2048
ALLOWED_PLATFORMS = frozenset(('pc', 'ps4', 'xboxone'))


def parse_soldier_url(raw):
    if not isinstance(raw, str) or len(raw) > 1024:
        raise ValueError('invalid URL')
    u = urlsplit(raw)
    if u.scheme != 'https' or u.netloc != 'battlelog.battlefield.com' or u.query or u.fragment:
        raise ValueError('invalid Battlelog URL')
    parts = u.path.strip('/').split('/')
    if len(parts) != 6 or parts[:2] != ['bf4', 'soldier'] or parts[3] != 'stats':
        raise ValueError('invalid soldier path')
    if not parts[2] or unquote(parts[2]) in ('.', '..') or parts[5] not in ALLOWED_PLATFORMS:
        raise ValueError('invalid soldier URL')
    if not parts[4].isascii() or not parts[4].isdigit():
        raise ValueError('invalid persona')
    persona = int(parts[4])
    if not 0 < persona < 2**63:
        raise ValueError('invalid persona')
    return persona, parts[5]


def submit(conn, url, kind):
    if kind not in ('add', 'refresh'):
        raise ValueError('invalid request kind')
    persona, platform = parse_soldier_url(url)
    row = conn.execute(text('''
        SELECT request_id, state, retry_after_seconds, jobs_created, jobs_promoted
        FROM manual_api.request_existing_soldier(:persona,:platform,:kind)
    '''), {'persona': persona, 'platform': platform, 'kind': kind}).mappings().one()
    return dict(row)


class Handler(BaseHTTPRequestHandler):
    # Intentionally local-only, with no CORS and no proxy IP-header trust.
    def respond(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/manual/request':
            return self.respond(404, {'error': 'not_found'})
        # Require explicit same-origin token at reverse proxy before any public rollout.
        # This private endpoint also requires a shared secret, configured separately.
        expected = os.environ.get('BF4PS_MANUAL_PRIVATE_TOKEN', '')
        if not expected:
            return self.respond(503, {'error': 'not_configured'})
        import hmac
        if not hmac.compare_digest(self.headers.get('X-BF4PS-Private-Token', ''), expected):
            return self.respond(403, {'error': 'forbidden'})
        length = self.headers.get('Content-Length', '')
        if not length.isascii() or not length.isdecimal() or not 0 < int(length) <= MAX_BODY:
            return self.respond(413, {'error': 'invalid_body_size'})
        if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
            return self.respond(415, {'error': 'unsupported_media_type'})
        try:
            payload = json.loads(self.rfile.read(int(length)))
            if not isinstance(payload, dict) or set(payload) != {'url', 'kind'}:
                raise ValueError('invalid payload')
            with self.server.engine.begin() as conn:
                result = submit(conn, payload['url'], payload['kind'])
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return self.respond(400, {'error': 'invalid_request'})
        except Exception:
            self.log_error('manual request backend failure')
            return self.respond(503, {'error': 'temporarily_unavailable'})
        return self.respond(200 if result['state'] in ('cooldown', 'up_to_date') else 202, result)

    def do_GET(self):
        return self.respond(404, {'error': 'not_found'})


def main():
    url = os.environ.get('BF4PS_MANUAL_DATABASE_URL', '')
    token = os.environ.get('BF4PS_MANUAL_PRIVATE_TOKEN', '')
    if not url or not token or len(token) < 32:
        raise SystemExit('private manual API requires separate DB URL and 32+ character token')
    server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('BF4PS_MANUAL_PORT', '8789'))), Handler)
    server.engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=1)
    server.serve_forever()


if __name__ == '__main__':
    main()