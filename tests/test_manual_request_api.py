import os
import sys
import unittest
import json
import threading
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from manual_request_api import parse_soldier_url, submit, main, SlidingWindowLimiter, Handler

URL = 'https://battlelog.battlefield.com/bf4/soldier/mauirixxx/stats/236753552/pc/'

class ManualApiTests(unittest.TestCase):
    def test_valid_url(self):
        self.assertEqual(parse_soldier_url(URL), (236753552, 'pc'))

    def test_bad_urls(self):
        for url in (
            'http://battlelog.battlefield.com/bf4/soldier/x/stats/123/pc/',
            'https://evil.example/bf4/soldier/x/stats/123/pc/',
            'https://battlelog.battlefield.com/bf4/soldier/x/stats/123/pc/?foo=1',
            'https://battlelog.battlefield.com/bf4/soldier/x/stats/0/pc/',
            'https://battlelog.battlefield.com/bf4/soldier/x/stats/123/ps3/',
            'https://battlelog.battlefield.com/bf4/soldier/x/stats/123/pc/extra',
            'https://battlelog.battlefield.com/bf4/soldier/x/stats/abc/pc/',
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_soldier_url(url)

    def test_only_approved_sql_function(self):
        class Conn:
            def execute(self, query, params):
                assert 'manual_api.request_existing_soldier' in str(query)
                assert params == {'persona':236753552,'platform':'pc','kind':'refresh'}
                return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: {
                    'request_id':1,'state':'accepted','retry_after_seconds':0,
                    'jobs_created':4,'jobs_promoted':0}))
        self.assertEqual(submit(Conn(), URL, 'refresh')['jobs_created'], 4)
        with self.assertRaises(ValueError):
            submit(Conn(), URL, 'urgent')

    def test_rate_limit_window(self):
        limiter = SlidingWindowLimiter(limit=2, window=60)
        self.assertTrue(limiter.allow('127.0.0.1', now=100))
        self.assertTrue(limiter.allow('127.0.0.1', now=101))
        self.assertFalse(limiter.allow('127.0.0.1', now=102))
        self.assertTrue(limiter.allow('127.0.0.1', now=161))

    def test_limiter_bounded_clients(self):
        limiter = SlidingWindowLimiter(limit=2, window=60, max_clients=1)
        self.assertTrue(limiter.allow('a', now=100))
        self.assertFalse(limiter.allow('b', now=101))
        self.assertTrue(limiter.allow('b', now=161))

    def test_http_auth_validation_and_rate_limit(self):
        class DummyEngine:
            def begin(self):
                raise AssertionError('unauthorized request must not reach DB')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.engine = DummyEngine()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {'BF4PS_MANUAL_PRIVATE_TOKEN':'x'*40,
                                       'BF4PS_MANUAL_ALLOWED_ORIGIN':'https://bf4playerstats.com'}):
                def post(headers):
                    client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
                    client.request('POST','/manual/request',body='{}',headers=headers)
                    response = client.getresponse()
                    result = response.status, dict(response.getheaders()), json.loads(response.read())
                    client.close()
                    return result
                status, _, _ = post({'Content-Type':'application/json','Content-Length':'2'})
                self.assertEqual(status,403)
                status, _, _ = post({'X-BF4PS-Private-Token':'x'*40,
                                    'Origin':'https://evil.example','Content-Type':'application/json'})
                self.assertEqual(status,403)
                status, _, _ = post({'X-BF4PS-Private-Token':'x'*40,
                                    'Origin':'https://bf4playerstats.com',
                                    'Content-Type':'application/json'})
                self.assertEqual(status,400)
                with patch('manual_request_api.LIMITER.allow', return_value=False):
                    status, headers, payload = post({
                        'X-BF4PS-Private-Token':'x'*40,
                        'Origin':'https://bf4playerstats.com',
                        'Content-Type':'application/json'})
                    self.assertEqual(status,429)
                    self.assertEqual(headers['Retry-After'],'60')
                    self.assertEqual(payload['error'],'rate_limited')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_no_credentials_no_startup(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            main()

if __name__ == '__main__':
    unittest.main()