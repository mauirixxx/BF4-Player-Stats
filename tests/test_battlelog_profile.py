import pytest

from bf4ps.battlelog_profile import ProfileFetchError, parse_profile_html, profile_url


def test_profile_url_encodes_username():
    assert profile_url("some user").endswith("/bf4/user/some%20user/")
    with pytest.raises(ValueError):
        profile_url("../someone")


def test_public_country():
    html = '<span class="location-information"><img src="/common/flags/us.gif" alt="United States"></span>'
    observed = parse_profile_html("mauirixxx", html)
    assert (observed.access_state, observed.country_code, observed.country_name) == (
        "public_country", "US", "United States"
    )


def test_friends_only_takes_priority_over_country():
    html = '<div> This user is only sharing their profile with friends </div><span class="location-information"><img src="/flags/us.gif"></span>'
    assert parse_profile_html("restricted", html).access_state == "friends_only"


def test_public_without_country():
    assert parse_profile_html("zgr1mm", "<section>Presentation</section>").access_state == "public_no_country"


def test_unrecognized_is_not_assumed_public():
    with pytest.raises(ProfileFetchError):
        parse_profile_html("missing", "<html><body>Unexpected response</body></html>")


def test_empty_is_error():
    with pytest.raises(ProfileFetchError):
        parse_profile_html("missing", "")
