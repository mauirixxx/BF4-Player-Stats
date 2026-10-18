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


def test_passive_platoon_observation_preserves_username():
    from bf4ps.account_resolution import parse_soldier_page
    html = '''<h1 class="soldier-info-name"><span>[HOLY]</span><span>mauirixxx</span></h1>
    <a class="profile-link" data-track="soldier.profile" href="/bf4/user/mauirixxx/">Profile</a>
    <span class="club-link">Platoon: <a href="/bf4/platoons/view/4452867151931601735/">UCAV Church</a></span>'''
    observation = parse_soldier_page(html)
    assert observation.username == 'mauirixxx'
    assert observation.displayed_tag == '[HOLY]'
    assert observation.linked_platoon_id == 4452867151931601735


def test_conflicting_platoon_links_are_not_inferred():
    from bf4ps.account_resolution import parse_soldier_page
    html = '''<a class="profile-link" data-track="soldier.profile" href="/bf4/user/test/">Profile</a>
    <a href="/bf4/platoons/view/123/">one</a><a href="/bf4/platoons/view/456/">two</a>'''
    assert parse_soldier_page(html).linked_platoon_id is None


def test_unrelated_platoon_link_does_not_count_as_active():
    from bf4ps.account_resolution import parse_soldier_page
    html = '''<a class="profile-link" data-track="soldier.profile" href="/bf4/user/test/">Profile</a>
    <a href="/bf4/platoons/view/123/">Unrelated link</a>'''
    assert parse_soldier_page(html).linked_platoon_id is None


def test_nested_club_link_and_unrelated_link():
    from bf4ps.account_resolution import parse_soldier_page
    html = '''<a class="profile-link" data-track="soldier.profile" href="/bf4/user/test/">Profile</a>
    <span class="club-link"><span><a href="/bf4/platoons/view/123/">Selected</a></span></span>
    <a href="/bf4/platoons/view/456/">Unrelated</a>'''
    assert parse_soldier_page(html).linked_platoon_id == 123
