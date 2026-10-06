"""Battlelog weapon-statistics fetch and normalization boundary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bf4ps.battlelog_detailed import BATTLELOG_BASE_URL, platform_int


class WeaponStatsError(Exception):
    """Base error for weapon-statistics collection."""


class WeaponStatsTransportError(WeaponStatsError):
    pass


class WeaponStatsHTTPError(WeaponStatsError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class WeaponStatsDecodeError(WeaponStatsError):
    pass


class WeaponStatsNormalizationError(WeaponStatsError):
    pass


@dataclass(frozen=True)
class WeaponFetchResult:
    persona_id: int
    platform: str
    platform_int: int
    payload: Mapping[str, Any]
    response_bytes: int


@dataclass(frozen=True)
class NormalizedWeaponStat:
    weapon_guid: str
    name: str
    slug: str | None
    category: str | None
    kills: int
    headshots: int
    shots_fired: int
    shots_hit: int
    time_equipped_seconds: int


def weapon_stats_url(persona_id: int, platform: str) -> str:
    if isinstance(persona_id, bool) or not isinstance(persona_id, int) or persona_id <= 0:
        raise ValueError("persona_id must be a positive integer")
    return (
        f"{BATTLELOG_BASE_URL}/bf4/warsawWeaponsPopulateStats/"
        f"{persona_id}/{platform_int(platform)}/stats/"
    )


def fetch_weapon_stats(
    persona_id: int,
    platform: str,
    *,
    timeout_seconds: float = 30.0,
) -> WeaponFetchResult:
    """Fetch one anonymous Battlelog weapon-statistics payload.

    Request pacing is intentionally outside this function. The collector must
    acquire the PostgreSQL-coordinated egress gate immediately before calling
    it. ``response_bytes`` records the actual HTTP entity body size read by
    BF4PS so Phase 5A can characterize measured payload cost.
    """
    p_int = platform_int(platform)
    request = Request(
        weapon_stats_url(persona_id, platform),
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
        raise WeaponStatsHTTPError(exc.code, f"Battlelog weapon request returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise WeaponStatsTransportError(f"Battlelog weapon request failed: {exc}") from exc

    if status != 200:
        raise WeaponStatsHTTPError(status, f"Battlelog weapon request returned HTTP {status}")

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeaponStatsDecodeError("Battlelog weapon response was not valid JSON") from exc

    if not isinstance(payload, dict):
        raise WeaponStatsDecodeError("Battlelog weapon response root must be a JSON object")

    return WeaponFetchResult(persona_id, platform, p_int, payload, len(body))


def _decimal(value: Any, source_name: str) -> Decimal:
    if value is None:
        raise WeaponStatsNormalizationError(f"{source_name}: required numeric value is missing")
    if isinstance(value, bool):
        raise WeaponStatsNormalizationError(f"{source_name}: boolean is not numeric")
    if isinstance(value, (int, float, Decimal, str)):
        try:
            result = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise WeaponStatsNormalizationError(f"{source_name}: invalid numeric value {value!r}") from exc
        if not result.is_finite():
            raise WeaponStatsNormalizationError(f"{source_name}: non-finite numeric value {value!r}")
        return result
    raise WeaponStatsNormalizationError(
        f"{source_name}: unsupported numeric type {type(value).__name__}"
    )


def _integer(value: Any, source_name: str) -> int:
    result = _decimal(value, source_name)
    integral = result.to_integral_value()
    if result != integral:
        raise WeaponStatsNormalizationError(f"{source_name}: expected integer, got {value!r}")
    integer = int(integral)
    if integer < 0:
        raise WeaponStatsNormalizationError(f"{source_name}: expected non-negative integer, got {value!r}")
    return integer


def _required_text(value: Any, source_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WeaponStatsNormalizationError(f"{source_name}: required non-empty string is missing")
    return value.strip()


def _optional_text(value: Any, source_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WeaponStatsNormalizationError(f"{source_name}: expected string or null")
    value = value.strip()
    return value or None


def _stats_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data")
    if data is None:
        return payload
    if not isinstance(data, Mapping):
        raise WeaponStatsNormalizationError("data is present but is not an object")
    return data


def _weapon_entries(stats: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return the verified Battlelog weapon-stat entry collection.

    Reconnaissance established ``mainWeaponStats`` as the retained weapon-stat
    collection. We deliberately do not search arbitrary nested payload values:
    an unexpected shape is a normalization failure, not permission to guess.
    """
    entries = stats.get("mainWeaponStats")
    if not isinstance(entries, list):
        raise WeaponStatsNormalizationError("mainWeaponStats is missing or is not an array")
    normalized_entries: list[Mapping[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise WeaponStatsNormalizationError(f"mainWeaponStats[{index}] is not an object")
        normalized_entries.append(entry)
    return normalized_entries


def normalize_weapon_stats(
    payload: Mapping[str, Any],
    *,
    expected_persona_id: int | None = None,
    expected_platform_int: int | None = None,
) -> list[NormalizedWeaponStat]:
    """Normalize Battlelog JSON to the frozen BF4PS weapon retention contract."""
    stats = _stats_payload(payload)

    if expected_persona_id is not None and "personaId" in stats:
        observed = _integer(stats.get("personaId"), "personaId")
        if observed != expected_persona_id:
            raise WeaponStatsNormalizationError(
                f"personaId mismatch: expected {expected_persona_id}, observed {observed}"
            )

    if expected_platform_int is not None and "platformInt" in stats:
        observed = _integer(stats.get("platformInt"), "platformInt")
        if observed != expected_platform_int:
            raise WeaponStatsNormalizationError(
                f"platformInt mismatch: expected {expected_platform_int}, observed {observed}"
            )

    result: list[NormalizedWeaponStat] = []
    seen_guids: set[str] = set()
    for index, entry in enumerate(_weapon_entries(stats)):
        prefix = f"mainWeaponStats[{index}]"
        guid = _required_text(entry.get("guid"), f"{prefix}.guid")
        if guid in seen_guids:
            raise WeaponStatsNormalizationError(f"duplicate weapon guid in payload: {guid!r}")
        seen_guids.add(guid)

        result.append(
            NormalizedWeaponStat(
                weapon_guid=guid,
                name=_required_text(entry.get("name"), f"{prefix}.name"),
                slug=_optional_text(entry.get("slug"), f"{prefix}.slug"),
                category=_optional_text(entry.get("category"), f"{prefix}.category"),
                kills=_integer(entry.get("kills"), f"{prefix}.kills"),
                headshots=_integer(entry.get("headshots"), f"{prefix}.headshots"),
                shots_fired=_integer(entry.get("shotsFired"), f"{prefix}.shotsFired"),
                shots_hit=_integer(entry.get("shotsHit"), f"{prefix}.shotsHit"),
                time_equipped_seconds=_integer(
                    entry.get("timeEquipped"), f"{prefix}.timeEquipped"
                ),
            )
        )
    return result
