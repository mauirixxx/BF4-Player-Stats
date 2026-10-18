"""Resolve a Battlelog account username from an authoritative BF4 soldier page.

This module deliberately does not guess usernames from soldier display names.
Network callers must account for each soldier-page request in the shared rate gate.
"""
from bf4ps.single_request_transport import single_request_urlopen
from html.parser import HTMLParser
from dataclasses import dataclass
import re
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen


class AccountResolutionError(ValueError):
    """Soldier page does not establish exactly one account relationship."""


@dataclass(frozen=True)
class SoldierPageObservation:
    username: str
    linked_platoon_id: int | None
    displayed_tag: str | None


class _AccountLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.platoons = []
        self.displayed_tag = None
        self._in_name = False
        self._in_tag = False
        self._in_club = False
        self._club_depth = 0
        self._name_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if tag == "h1" and "soldier-info-name" in classes:
            self._in_name = True
            self._name_depth = 1
        elif self._in_name and tag == "span":
            self._name_depth += 1
            if self.displayed_tag is None:
                self._in_tag = True
        if tag == "span" and "club-link" in classes:
            self._in_club = True
            self._club_depth = 1
        elif self._in_club and tag == "span":
            self._club_depth += 1
        if tag != "a":
            return
        match = re.fullmatch(r"/bf4/platoons/view/([1-9][0-9]{0,18})/", attrs.get("href") or "")
        if match and self._in_club:
            self.platoons.append(int(match.group(1)))
        if attrs.get("data-track") != "soldier.profile":
            return
        if "profile-link" not in (attrs.get("class") or "").split():
            return
        self.links.append(attrs.get("href") or "")

    def handle_endtag(self, tag):
        if tag == "span" and self._in_club:
            self._club_depth -= 1
            if self._club_depth == 0:
                self._in_club = False
        if self._in_name and tag in ("span", "h1"):
            if tag == "span":
                self._in_tag = False
            self._name_depth -= 1
            if self._name_depth == 0:
                self._in_name = False

    def handle_data(self, data):
        value = data.strip()
        if self._in_tag and self.displayed_tag is None and value.startswith("[") and value.endswith("]"):
            self.displayed_tag = value


def soldier_url(name: str, persona_id: int, platform: str) -> str:
    if not name or "/" in name or not str(persona_id).isdigit():
        raise ValueError("invalid soldier identity")
    if platform not in ("pc", "ps4", "xboxone"):
        raise ValueError("unsupported platform")
    return (f"https://battlelog.battlefield.com/bf4/soldier/"
            f"{quote(name.strip(), safe='')}/stats/{int(persona_id)}/{platform}/")


def parse_soldier_page(html: str) -> SoldierPageObservation:
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
    ids = set(parser.platoons)
    return SoldierPageObservation(usernames.pop(), next(iter(ids)) if len(ids) == 1 else None, parser.displayed_tag)


def resolve_account_username(html: str) -> str:
    return parse_soldier_page(html).username


def fetch_account_observation(name: str, persona_id: int, platform: str, *, timeout_seconds: float = 30.0) -> SoldierPageObservation:
    """Fetch soldier HTML and extract its account link; caller must reserve a request slot."""
    request = Request(soldier_url(name, persona_id, platform), headers={
        "Accept": "text/html",
        "User-Agent": "BF4PlayerStats/0.1 (+https://bf4playerstats.com)",
    })
    with single_request_urlopen(request, timeout=timeout_seconds) as response:
        if response.status != 200:
            raise AccountResolutionError(f"soldier page HTTP {response.status}")
        body = response.read()
    return parse_soldier_page(body.decode("utf-8"))


def fetch_account_username(name: str, persona_id: int, platform: str, *, timeout_seconds: float = 30.0) -> str:
    return fetch_account_observation(name, persona_id, platform, timeout_seconds=timeout_seconds).username
