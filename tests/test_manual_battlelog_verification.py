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
