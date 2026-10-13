"""Anonymous Battlelog profile HTML fetch and conservative classification.

Profile enrichment is optional. Never infer account ownership from a soldier name.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import re


class ProfileFetchError(Exception):
    """Network, HTTP, or unrecognized response; do not mark profile successful."""


@dataclass(frozen=True)
class ProfileObservation:
    username: str
    access_state: str
    country_code: str | None
    country_name: str | None


class _ProfileHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.flag_candidates: list[tuple[str, str | None]] = []
        self._stack: list[tuple[str, bool]] = []
        self._location_count = 0
        self.text_parts: list[str] = []
        self.has_presentation = False

    _VOID_TAGS = frozenset({
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    })

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        is_location = "location-information" in classes
        if is_location:
            self._location_count += 1
        if self._location_count and tag == "img":
            match = re.search(r"/flags/([a-z]{2})\\.gif(?:[?#]|$)", a.get("src") or "", re.I)
            if match:
                self.flag_candidates.append(
                    (match.group(1).upper(), a.get("alt") or a.get("data-tooltip"))
                )
        if "presentation" in classes:
            self.has_presentation = True
        if tag not in self._VOID_TAGS:
            self._stack.append((tag, is_location))
        elif is_location:
            self._location_count -= 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                removed = self._stack[i:]
                self._stack = self._stack[:i]
                self._location_count -= sum(1 for _, location in removed if location)
                break

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)


def profile_url(username: str) -> str:
    if not isinstance(username, str) or not username.strip() or "/" in username:
        raise ValueError("Battlelog username must be nonempty and contain no slash")
    return "https://battlelog.battlefield.com/bf4/user/" + quote(username.strip(), safe="") + "/"


def parse_profile_html(username: str, html: str) -> ProfileObservation:
    if not html.strip():
        raise ProfileFetchError("empty Battlelog profile HTML")
    parser = _ProfileHTML()
    parser.feed(html)
    text = " ".join(parser.text_parts).casefold()
    if "only sharing" in text and "friends" in text:
        return ProfileObservation(username, "friends_only", None, None)
    if len(parser.flag_candidates) > 1 and len(set(parser.flag_candidates)) > 1:
        raise ProfileFetchError("ambiguous country flags")
    if parser.flag_candidates:
        code, name = parser.flag_candidates[0]
        return ProfileObservation(username, "public_country", code, name)
    if parser.has_presentation or "presentation" in text:
        return ProfileObservation(username, "public_no_country", None, None)
    raise ProfileFetchError("unrecognized Battlelog profile HTML; not safe to classify")


def fetch_profile(username: str, *, timeout_seconds: float = 15.0) -> ProfileObservation:
    request = Request(profile_url(username), headers={
        "Accept": "text/html",
        "User-Agent": "BF4PlayerStats/0.1 (+https://bf4playerstats.com)",
    })
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise ProfileFetchError(f"Battlelog profile HTTP {response.status}")
            body = response.read()
    except HTTPError as exc:
        raise ProfileFetchError(f"Battlelog profile HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProfileFetchError("Battlelog profile transport failure") from exc
    try:
        html = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProfileFetchError("invalid profile HTML encoding") from exc
    return parse_profile_html(username, html)
