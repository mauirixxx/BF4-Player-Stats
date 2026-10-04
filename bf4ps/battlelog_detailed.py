"""Battlelog detailed-statistics fetch and normalization boundary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BATTLELOG_BASE_URL = "https://battlelog.battlefield.com"
PLATFORM_INTS = {"pc": 1, "ps4": 32, "xboxone": 64}


class DetailedStatsError(Exception):
    """Base error for detailed-statistics collection."""


class UnsupportedPlatformError(DetailedStatsError):
    pass


class DetailedStatsTransportError(DetailedStatsError):
    pass


class DetailedStatsHTTPError(DetailedStatsError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class DetailedStatsDecodeError(DetailedStatsError):
    pass


class DetailedStatsNormalizationError(DetailedStatsError):
    pass


@dataclass(frozen=True)
class DetailedFetchResult:
    persona_id: int
    platform: str
    platform_int: int
    payload: Mapping[str, Any]


# DB column -> Battlelog generalStats field.  These are exactly the RAW values
# frozen by Detailed Stats Retention Contract v1.
INTEGER_FIELDS = {
    "rank": "rank",
    "time_played_seconds": "timePlayed",
    "assault_score": "assault",
    "engineer_score": "engineer",
    "support_score": "support",
    "recon_score": "recon",
    "commander_score": "commander",
    "squad_score": "sc_squad",
    "vehicle_score": "sc_vehicle",
    "award_score": "sc_award",
    "unlock_score": "sc_unlock",
    "total_score": "score",
    "combat_score": "combatScore",
    "conquest_score": "conquest",
    "rush_score": "rush",
    "team_deathmatch_score": "teamdeathmatch",
    "domination_score": "domination",
    "obliteration_score": "obliteration",
    "defuse_score": "elimination",
    "capture_the_flag_score": "capturetheflag",
    "air_superiority_score": "airsuperiority",
    "carrier_assault_score": "carrierassault",
    "chain_link_score": "chainlink",
    "gun_master_score": "gunmaster",
    "kills": "kills",
    "deaths": "deaths",
    "kill_assists": "killAssists",
    "wins": "numWins",
    "losses": "numLosses",
    "shots_fired": "shotsFired",
    "shots_hit": "shotsHit",
    "repairs": "repairs",
    "revives": "revives",
    "heals": "heals",
    "resupplies": "resupplies",
    "avenger_kills": "avengerKills",
    "savior_kills": "saviorKills",
    "suppression_assists": "suppressionAssists",
    "flags_captured": "flagCaptures",
    "flags_defended": "flagDefend",
    "dogtags_taken": "dogtagsTaken",
    "vehicles_destroyed": "vehiclesDestroyed",
    "vehicle_damage": "vehicleDamage",
    "headshots": "headshots",
    "highest_kill_streak": "killStreakBonus",
    "nemesis_kills": "nemesisKills",
    "highest_nemesis_streak": "nemesisStreak",
}

DECIMAL_FIELDS = {
    "quit_percentage": "quitPercentage",
    "longest_headshot": "longestHeadshot",
}


def platform_int(platform: str) -> int:
    try:
        return PLATFORM_INTS[platform]
    except KeyError as exc:
        raise UnsupportedPlatformError(f"unsupported BF4 platform: {platform!r}") from exc


def detailed_stats_url(persona_id: int, platform: str) -> str:
    if isinstance(persona_id, bool) or not isinstance(persona_id, int) or persona_id <= 0:
        raise ValueError("persona_id must be a positive integer")
    return (
        f"{BATTLELOG_BASE_URL}/bf4/warsawdetailedstatspopulate/"
        f"{persona_id}/{platform_int(platform)}/"
    )


def fetch_detailed_stats(
    persona_id: int,
    platform: str,
    *,
    timeout_seconds: float = 15.0,
) -> DetailedFetchResult:
    """Fetch one anonymous Battlelog detailed-statistics payload.

    Request pacing is intentionally outside this function: the collector must
    acquire the database-coordinated egress gate immediately before calling it.
    """
    p_int = platform_int(platform)
    url = detailed_stats_url(persona_id, platform)
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "BF4PlayerStats/0.1 (+https://bf4playerstats.com)",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 200)
            body = response.read()
    except HTTPError as exc:
        raise DetailedStatsHTTPError(exc.code, f"Battlelog detailed request returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DetailedStatsTransportError(f"Battlelog detailed request failed: {exc}") from exc

    if status != 200:
        raise DetailedStatsHTTPError(status, f"Battlelog detailed request returned HTTP {status}")

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DetailedStatsDecodeError("Battlelog detailed response was not valid JSON") from exc

    if not isinstance(payload, dict):
        raise DetailedStatsDecodeError("Battlelog detailed response root must be a JSON object")

    return DetailedFetchResult(persona_id, platform, p_int, payload)


def _decimal(value: Any, source_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise DetailedStatsNormalizationError(f"{source_name}: boolean is not numeric")
    if isinstance(value, (int, float, Decimal, str)):
        try:
            result = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise DetailedStatsNormalizationError(f"{source_name}: invalid numeric value {value!r}") from exc
        if not result.is_finite():
            raise DetailedStatsNormalizationError(f"{source_name}: non-finite numeric value {value!r}")
        return result
    raise DetailedStatsNormalizationError(f"{source_name}: unsupported numeric type {type(value).__name__}")


def _integer(value: Any, source_name: str) -> int | None:
    result = _decimal(value, source_name)
    if result is None:
        return None
    integral = result.to_integral_value()
    if result != integral:
        raise DetailedStatsNormalizationError(f"{source_name}: expected integer, got {value!r}")
    return int(integral)


def _stats_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the statistics object from Battlelog's live response envelope.

    The live endpoint returns ``{"type": ..., "message": ..., "data": {...}}``.
    Keeping the unwrapping at the normalization boundary also permits fixture
    payloads that already represent the inner data object.
    """
    data = payload.get("data")
    if data is None:
        return payload
    if not isinstance(data, Mapping):
        raise DetailedStatsNormalizationError("data is present but is not an object")
    return data


def normalize_detailed_stats(
    payload: Mapping[str, Any],
    *,
    expected_persona_id: int | None = None,
    expected_platform_int: int | None = None,
) -> dict[str, int | Decimal | None]:
    """Normalize Battlelog JSON to Detailed Stats Retention Contract v1."""
    stats = _stats_payload(payload)
    general = stats.get("generalStats")
    if not isinstance(general, Mapping):
        raise DetailedStatsNormalizationError("generalStats is missing or is not an object")

    if expected_persona_id is not None and "personaId" in stats:
        observed = _integer(stats.get("personaId"), "personaId")
        if observed != expected_persona_id:
            raise DetailedStatsNormalizationError(
                f"personaId mismatch: expected {expected_persona_id}, observed {observed}"
            )

    if expected_platform_int is not None and "platformInt" in stats:
        observed = _integer(stats.get("platformInt"), "platformInt")
        if observed != expected_platform_int:
            raise DetailedStatsNormalizationError(
                f"platformInt mismatch: expected {expected_platform_int}, observed {observed}"
            )

    normalized: dict[str, int | Decimal | None] = {}
    for column, source in INTEGER_FIELDS.items():
        normalized[column] = _integer(general.get(source), source)
    for column, source in DECIMAL_FIELDS.items():
        normalized[column] = _decimal(general.get(source), source)
    return normalized
