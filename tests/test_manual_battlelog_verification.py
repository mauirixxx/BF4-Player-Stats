from contextlib import contextmanager
from unittest.mock import patch
import pytest

from bf4ps.manual_battlelog_verification import (
    SoldierVerificationError, verify_soldier_html,
)

URL = "https://battlelog.battlefield.com/bf4/soldier/mauirixxx/stats/236753552/pc/"


def test_confirm_matching_identity_from_battlelog_html():
    html = '<a href="/bf4/soldier/mauirixxx/stats/236753552/pc/">Soldier</a>'
    result = verify_soldier_html(URL, html)
    assert (result.persona_id, result.platform, result.current_name) == (
        236753552, "pc", "mauirixxx")


def test_reject_missing_identity():
    with pytest.raises(SoldierVerificationError):
        verify_soldier_html(URL, "<html>no soldier</html>")


def test_reject_other_persona():
    with pytest.raises(SoldierVerificationError):
        verify_soldier_html(
            URL, '<a href="/bf4/soldier/mauirixxx/stats/236753553/pc/">Wrong</a>')


def test_reject_ambiguous_names():
    with pytest.raises(SoldierVerificationError):
        verify_soldier_html(URL, (
            '<a href="/bf4/soldier/one/stats/236753552/pc/">One</a>'
            '<a href="/bf4/soldier/two/stats/236753552/pc/">Two</a>'))


def test_fetch_requires_dispatch_context_and_never_calls_network_without_it():
    from bf4ps.manual_battlelog_verification import fetch_verified_soldier
    with patch('bf4ps.manual_battlelog_verification.single_request_urlopen') as network:
        with pytest.raises(TypeError):
            fetch_verified_soldier(URL, authorized_dispatch=None)
        network.assert_not_called()


def test_fetch_uses_one_authorized_request():
    from bf4ps.manual_battlelog_verification import fetch_verified_soldier
    entered = []

    @contextmanager
    def dispatch():
        entered.append(True)
        yield

    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, n):
            return b'<a href="/bf4/soldier/mauirixxx/stats/236753552/pc/">ok</a>'

    with patch('bf4ps.manual_battlelog_verification.single_request_urlopen', return_value=Response()) as network:
        result = fetch_verified_soldier(URL, authorized_dispatch=dispatch)
    assert entered == [True]
    assert result.persona_id == 236753552
    network.assert_called_once()
