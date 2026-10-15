import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from manual_request_api import parse_soldier_url, submit, main

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

    def test_no_credentials_no_startup(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            main()

if __name__ == '__main__':
    unittest.main()