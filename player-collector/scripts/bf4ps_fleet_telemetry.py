#!/usr/bin/env python3
"""Read-only BF4PS fleet service telemetry. Internal network only."""
import json
import os
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED = {'192.168.10.71', '127.0.0.1', '::1'}
SERVICES = (
    'bf4ps-platoon-alternating.service',
    'bf4ps-platoon-alternating.timer',
    'bf4ps-platoon-queue.service',
    'bf4ps-platoon-queue.timer',
    'bf4ps-platoon-discovery.timer',
    'bf4ps-platoon-refresh.timer',
    'bf4ps-compact-ranking.service',
    'bf4ps-watchdog.timer',
    'bf4ps-watchdog.service',
    'bf4ps-weapon-metrics-sync.service',
    'bf4ps-vehicle-metrics-sync.service',
)
CONTAINERS = ('bf4ps-production-collector', 'bf4ps-compact-ranking', 'bf4ps-discord-ha-mak', 'bf4ps-discord-ha-rnt')

def snapshot():
    result = {'host': socket.gethostname(), 'at': time.time(), 'services': {}, 'containers': {}, 'images': {}}
    for unit in SERVICES:
        proc = subprocess.run(['systemctl', 'show', unit, '--property=LoadState,ActiveState,SubState,Result,UnitFileState'],
                              capture_output=True, text=True, timeout=2)
        props = dict(line.split('=', 1) for line in proc.stdout.splitlines() if '=' in line)
        if props.get('LoadState') != 'not-found':
            result['services'][unit] = props
    try:
        # Inspect separately to avoid positional ambiguity for absent containers.
        for name in CONTAINERS:
            p = subprocess.run(['docker', 'inspect', '--format', '{{.State.Status}}|{{.Config.Image}}', name],
                               capture_output=True, text=True, timeout=2)
            if p.returncode == 0:
                state, image = p.stdout.strip().split('|', 1)
                result['containers'][name] = state
                result['images'][name] = image
    except (OSError, subprocess.TimeoutExpired):
        pass
    return result

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.client_address[0] not in ALLOWED or self.path != '/status':
            self.send_error(403)
            return
        try:
            body = json.dumps(snapshot()).encode()
        except Exception:
            self.send_error(503)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, fmt, *args):
        return

if __name__ == '__main__':
    bind = os.environ.get('BF4PS_TELEMETRY_BIND', '127.0.0.1')
    ThreadingHTTPServer((bind, 8772), Handler).serve_forever()
