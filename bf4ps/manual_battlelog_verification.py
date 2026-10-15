"""Validate Battlelog soldier HTML before admitting a manually submitted URL.

Pure parsing only. Network requests must use the fleet's existing dispatch gate.
"""
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import re

from bf4ps.manual_battlelog_url import parse_battlelog_soldier_url
from bf4ps.manual_verified_ingestion import VerifiedSoldier


class SoldierVerificationError(ValueError):
    pass


class _SoldierLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.matches = set()

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            return
        match = re.fullmatch(
            r"/bf4/soldier/([^/]+)/stats/([1-9][0-9]{0,18})/(pc|ps4|xboxone)/?",
            parsed.path)
        if match:
            self.matches.add((int(match.group(2)), match.group(3),
                              unquote(match.group(1))))


def verify_soldier_html(url: str, html: str) -> VerifiedSoldier:
    identity = parse_battlelog_soldier_url(url)
    parser = _SoldierLinks()
    parser.feed(html)
    matches = {(persona, platform, name) for persona, platform, name in parser.matches
               if persona == identity.persona_id and platform == identity.platform}
    if len(matches) != 1:
        raise SoldierVerificationError("Battlelog page did not confirm one matching soldier")
    _, _, name = matches.pop()
    if not name or len(name) > 255:
        raise SoldierVerificationError("Invalid soldier name in Battlelog response")
    return VerifiedSoldier(identity.persona_id, identity.platform, name)
