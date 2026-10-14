"""Resolve a Battlelog account username from an authoritative BF4 soldier page.

This module deliberately does not guess usernames from soldier display names.
Network callers must account for each soldier-page request in the shared rate gate.
"""
from bf4ps.single_request_transport import single_request_urlopen
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen


class AccountResolutionError(ValueError):
    """Soldier page does not establish exactly one account relationship."""


class _AccountLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attrs = dict(attrs)
        if attrs.get("data-track") != "soldier.profile":
            return
        if "profile-link" not in (attrs.get("class") or "").split():
            return
        self.links.append(attrs.get("href") or "")


def soldier_url(name: str, persona_id: int, platform: str) -> str:
    if not name or "/" in name or not str(persona_id).isdigit():
        raise ValueError("invalid soldier identity")
    if platform not in ("pc", "ps4", "xboxone"):
        raise ValueError("unsupported platform")
    return (f"https://battlelog.battlefield.com/bf4/soldier/"
            f"{quote(name.strip(), safe='')}/stats/{int(persona_id)}/{platform}/")


def resolve_account_username(html: str) -> str:
    parser = _AccountLinkParser()
    parser.feed(html)
    usernames = set()
    for href in parser.links:
        path = urlsplit(href)
        if path.scheme or path.netloc:
            raise AccountResolutionError("unexpected absolute account link")
        segments = path.path.split("/")
        if len(segments) != 5 or segments[:3] != ["", "bf4", "user"] or segments[4]:
            raise AccountResolutionError("unexpected account link path")
        username = unquote(segments[3])
        if not username or "/" in username:
            raise AccountResolutionError("invalid account username")
        usernames.add(username)
    if len(usernames) != 1:
        raise AccountResolutionError(f"expected one account link; found {len(usernames)}")
    return usernames.pop()


def fetch_account_username(name: str, persona_id: int, platform: str, *, timeout_seconds: float = 30.0) -> str:
    """Fetch soldier HTML and extract its account link; caller must reserve a request slot."""
    request = Request(soldier_url(name, persona_id, platform), headers={
        "Accept": "text/html",
        "User-Agent": "BF4PlayerStats/0.1 (+https://bf4playerstats.com)",
    })
    with single_request_urlopen(request, timeout=timeout_seconds) as response:
        if response.status != 200:
            raise AccountResolutionError(f"soldier page HTTP {response.status}")
        body = response.read()
    return resolve_account_username(body.decode("utf-8"))
