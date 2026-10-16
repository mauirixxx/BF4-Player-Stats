import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from admin_console_api import sign_session, read_session, csrf_for, check_password, login_allowed, record_login_failure, _login_failures


class AdminAuthTests(unittest.TestCase):
    def setUp(self):
        self.secret = 'a' * 64

    def test_valid_signed_session_and_csrf(self):
        token = sign_session('moderator', self.secret, now=1000)
        session = read_session(token, 'moderator', self.secret, now=1100)
        self.assertIsNotNone(session)
        self.assertEqual(len(csrf_for(session, self.secret)), 64)

    def test_session_expiration_and_wrong_identity(self):
        token = sign_session('moderator', self.secret, now=1000)
        self.assertIsNone(read_session(token, 'moderator', self.secret, now=4600))
        self.assertIsNone(read_session(token, 'other', self.secret, now=1001))

    def test_tampering_and_wrong_secret(self):
        token = sign_session('moderator', self.secret, now=1000)
        self.assertIsNone(read_session(token + 'x', 'moderator', self.secret, now=1001))
        self.assertIsNone(read_session(token, 'moderator', 'b' * 64, now=1001))

    def test_failed_login_throttling(self):
        _login_failures.clear()
        for _ in range(10):
            record_login_failure(now=100)
        self.assertFalse(login_allowed(now=101))
        self.assertTrue(login_allowed(now=1000))
        _login_failures.clear()

    def test_pbkdf2_verification(self):
        salt = 'a' * 32
        digest = hashlib.pbkdf2_hmac('sha256', b'testpassword', salt.encode(), 600000).hex()
        self.assertTrue(check_password('testpassword', salt + '$' + digest))
        self.assertFalse(check_password('incorrect', salt + '$' + digest))


if __name__ == '__main__':
    unittest.main()
