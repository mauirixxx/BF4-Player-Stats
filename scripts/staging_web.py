#!/usr/bin/env python3
"""Loopback-only BF4PS frontend staging server. Never use as a public server."""
import http.client
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1] / "site"
SNAPSHOT = Path("/var/www/bf4playerstats.com/temp-stats-data.json")
API_PORT = int(os.environ.get("BF4PS_STAGING_API_PORT", "8766"))
PORT = int(os.environ.get("BF4PS_STAGING_WEB_PORT", "8877"))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/temp-stats-data.json":
            try:
                body = SNAPSHOT.read_bytes()
            except OSError:
                self.send_error(503, "Snapshot unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/bf4ps-api/"):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", API_PORT, timeout=10)
                conn.request("GET", "/" + path.removeprefix("/bf4ps-api/") + ("?" + urlsplit(self.path).query if urlsplit(self.path).query else ""))
                response = conn.getresponse()
                body = response.read()
                self.send_response(response.status)
                for name in ("Content-Type", "Cache-Control", "Retry-After", "X-Content-Type-Options"):
                    value = response.getheader(name)
                    if value: self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                conn.close()
            except (OSError, TimeoutError):
                body = b'{"status":"unavailable"}'
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        return super().do_GET()

if __name__ == "__main__":
    if not (1 <= API_PORT <= 65535 and 1 <= PORT <= 65535):
        raise ValueError("Invalid port")
    print(f"BF4PS staging only: http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
