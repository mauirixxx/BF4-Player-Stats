"""Validate Battlelog soldier HTML before admitting a manually submitted URL.

Network requests require a caller-supplied, preauthorized dispatch permit.
The caller must account for the physical HTTP attempt in the fleet budget.
"""
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
from urllib.request import Request
import re

from bf4ps.single_request_transport import single_request_urlopen

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


def fetch_verified_soldier(url: str, *, authorized_dispatch,
                           timeout_seconds: float = 15.0) -> VerifiedSoldier:
    """Fetch exactly one soldier page only after a trusted dispatch authorization.

    The caller must reserve pacing AND physical dispatch budget first. This
    low-level helper deliberately cannot issue an unaccounted request by default.
    """
    parse_battlelog_soldier_url(url)
    if not callable(authorized_dispatch):
        raise TypeError('authorized_dispatch must be a dispatch context factory')
    request = Request(url, headers={'Accept': 'text/html',
        'User-Agent': 'BF4PlayerStats/0.1 (+https://bf4playerstats.com)'})
    with authorized_dispatch():
        with single_request_urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise SoldierVerificationError(f'Battlelog HTTP {response.status}')
            body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise SoldierVerificationError('Battlelog page too large')
    try:
        html = body.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise SoldierVerificationError('Invalid Battlelog page encoding') from exc
    return verify_soldier_html(url, html)
