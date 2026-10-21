from bf4ps.account_resolution import resolve_account_username, soldier_url, AccountResolutionError
import pytest


@pytest.mark.parametrize("soldier,persona,platform,account", [
    ("How Do You Roam", 2012138562, "xboxone", "HowDoYouRoam"),
    ("a SAHF Satan", 226994796, "xboxone", "m2fgc0qjp2"),
    ("DA-DUKE", 886162551, "ps4", "jcgrief"),
    ("DryBones444", 890895330, "ps4", "dc7155f7f8f66171"),
])
def test_authoritative_account_link(soldier, persona, platform, account):
    assert f"/stats/{persona}/{platform}/" in soldier_url(soldier, persona, platform)
    html = f'<a class="profile-link" data-track="soldier.profile" href="/bf4/user/{account}/">Profile</a>'
    assert resolve_account_username(html) == account


def test_missing_or_conflicting_links_fail_closed():
    with pytest.raises(AccountResolutionError):
        resolve_account_username("<html><body>Not found</body></html>")
    with pytest.raises(AccountResolutionError):
        resolve_account_username('<a class="profile-link" data-track="soldier.profile" href="/bf4/user/a/"></a><a class="profile-link" data-track="soldier.profile" href="/bf4/user/b/"></a>')
