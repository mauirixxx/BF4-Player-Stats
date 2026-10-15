"""Strict, network-free parser for player-submitted BF4 Battlelog soldier URLs."""
from dataclasses import dataclass
from urllib.parse import urlsplit, unquote
import re

_PLATFORMS = {"pc": "pc", "ps4": "ps4", "xboxone": "xboxone"}
_SEGMENT = re.compile(r"^[A-Za-z0-9_.~-]{1,80}$")
_PERSONA = re.compile(r"^[1-9][0-9]{0,18}$")


@dataclass(frozen=True)
class BattlelogSoldier:
    persona_id: int
    platform: str
    soldier_name: str


def parse_battlelog_soldier_url(raw: str) -> BattlelogSoldier:
    if not isinstance(raw, str) or len(raw) > 512 or raw != raw.strip():
        raise ValueError("Invalid Battlelog URL")
    try:
        url = urlsplit(raw)
        host = url.hostname
        port = url.port
    except ValueError as exc:
        raise ValueError("Invalid Battlelog URL") from exc
    if (url.scheme != "https" or host != "battlelog.battlefield.com"
            or port is not None or url.username is not None or url.password is not None
            or url.query or url.fragment):
        raise ValueError("Expected an HTTPS Battlelog soldier URL")
    parts = url.path.strip("/").split("/")
    if len(parts) != 6 or parts[0:2] != ["bf4", "soldier"] or parts[3] != "stats":
        raise ValueError("Expected /bf4/soldier/NAME/stats/PERSONA/PLATFORM/")
    name = unquote(parts[2])
    if not _SEGMENT.fullmatch(name) or not _PERSONA.fullmatch(parts[4]) or parts[5] not in _PLATFORMS:
        raise ValueError("Invalid soldier name, persona ID or platform")
    persona = int(parts[4])
    if persona > 9223372036854775807:
        raise ValueError("Persona ID is out of range")
    return BattlelogSoldier(persona_id=persona, platform=parts[5], soldier_name=name)