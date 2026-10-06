"""Battlelog vehicle-statistics fetch and normalization boundary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bf4ps.battlelog_detailed import BATTLELOG_BASE_URL, platform_int


class VehicleStatsError(Exception):
    """Base error for vehicle-statistics collection."""


class VehicleStatsTransportError(VehicleStatsError):
    pass


class VehicleStatsHTTPError(VehicleStatsError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class VehicleStatsDecodeError(VehicleStatsError):
    pass


class VehicleStatsNormalizationError(VehicleStatsError):
    pass


@dataclass(frozen=True)
class VehicleFetchResult:
    persona_id: int
    platform: str
    platform_int: int
    payload: Mapping[str, Any]
    response_bytes: int


@dataclass(frozen=True)
class NormalizedVehicleStat:
    vehicle_guid: str
    name: str
    slug: str | None
    category: str | None
    kills: int
    time_in_seconds: int
    destroy_x_in_y: Decimal | None


def vehicle_stats_url(persona_id: int, platform: str) -> str:
    if isinstance(persona_id, bool) or not isinstance(persona_id, int) or persona_id <= 0:
        raise ValueError("persona_id must be a positive integer")
    return (
        f"{BATTLELOG_BASE_URL}/bf4/warsawvehiclesPopulateStats/"
        f"{persona_id}/{platform_int(platform)}/stats/"
    )


def fetch_vehicle_stats(
    persona_id: int,
    platform: str,
    *,
    timeout_seconds: float = 30.0,
) -> VehicleFetchResult:
    """Fetch one anonymous Battlelog vehicle-statistics payload."""
    p_int = platform_int(platform)
    request = Request(
        vehicle_stats_url(persona_id, platform),
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
        raise VehicleStatsHTTPError(
            exc.code, f"Battlelog vehicle request returned HTTP {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise VehicleStatsTransportError(f"Battlelog vehicle request failed: {exc}") from exc

    if status != 200:
        raise VehicleStatsHTTPError(status, f"Battlelog vehicle request returned HTTP {status}")

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleStatsDecodeError("Battlelog vehicle response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise VehicleStatsDecodeError("Battlelog vehicle response root must be a JSON object")
    return VehicleFetchResult(persona_id, platform, p_int, payload, len(body))


def _decimal(value: Any, source_name: str) -> Decimal:
    if value is None:
        raise VehicleStatsNormalizationError(f"{source_name}: required numeric value is missing")
    if isinstance(value, bool):
        raise VehicleStatsNormalizationError(f"{source_name}: boolean is not numeric")
    if isinstance(value, (int, float, Decimal, str)):
        try:
            result = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise VehicleStatsNormalizationError(
                f"{source_name}: invalid numeric value {value!r}"
            ) from exc
        if not result.is_finite():
            raise VehicleStatsNormalizationError(
                f"{source_name}: non-finite numeric value {value!r}"
            )
        if result < 0:
            raise VehicleStatsNormalizationError(
                f"{source_name}: expected non-negative numeric value, got {value!r}"
            )
        return result
    raise VehicleStatsNormalizationError(
        f"{source_name}: unsupported numeric type {type(value).__name__}"
    )


def _integer(value: Any, source_name: str) -> int:
    result = _decimal(value, source_name)
    integral = result.to_integral_value()
    if result != integral:
        raise VehicleStatsNormalizationError(
            f"{source_name}: expected integer, got {value!r}"
        )
    return int(integral)


def _required_text(value: Any, source_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VehicleStatsNormalizationError(
            f"{source_name}: required non-empty string is missing"
        )
    return value.strip()


def _optional_text(value: Any, source_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise VehicleStatsNormalizationError(f"{source_name}: expected string or null")
    value = value.strip()
    return value or None


def _stats_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise VehicleStatsNormalizationError("data is missing or is not an object")
    return data


def _vehicle_entries(stats: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    entries = stats.get("mainVehicleStats")
    if not isinstance(entries, list):
        raise VehicleStatsNormalizationError(
            "mainVehicleStats is missing or is not an array"
        )
    result: list[Mapping[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise VehicleStatsNormalizationError(
                f"mainVehicleStats[{index}] is not an object"
            )
        result.append(entry)
    return result


def normalize_vehicle_stats(
    payload: Mapping[str, Any],
    *,
    expected_persona_id: int | None = None,
    expected_platform_int: int | None = None,
) -> list[NormalizedVehicleStat]:
    """Normalize Battlelog JSON to the frozen BF4PS vehicle retention contract."""
    stats = _stats_payload(payload)

    if expected_persona_id is not None:
        observed = _integer(stats.get("personaId"), "personaId")
        if observed != expected_persona_id:
            raise VehicleStatsNormalizationError(
                f"personaId mismatch: expected {expected_persona_id}, observed {observed}"
            )
    if expected_platform_int is not None:
        observed = _integer(stats.get("platformInt"), "platformInt")
        if observed != expected_platform_int:
            raise VehicleStatsNormalizationError(
                f"platformInt mismatch: expected {expected_platform_int}, observed {observed}"
            )

    result: list[NormalizedVehicleStat] = []
    seen_guids: set[str] = set()
    for index, entry in enumerate(_vehicle_entries(stats)):
        prefix = f"mainVehicleStats[{index}]"
        guid = _required_text(entry.get("guid"), f"{prefix}.guid")
        if guid in seen_guids:
            raise VehicleStatsNormalizationError(
                f"duplicate vehicle guid in payload: {guid!r}"
            )
        seen_guids.add(guid)

        # destroyXinY exists in the documented schema and was present as a
        # numeric value in live validation. Preserve explicit null if Battlelog
        # uses it for a vehicle where the metric is not applicable.
        raw_destroy = entry.get("destroyXinY")
        destroy = None if raw_destroy is None else _decimal(
            raw_destroy, f"{prefix}.destroyXinY"
        )
        result.append(
            NormalizedVehicleStat(
                vehicle_guid=guid,
                name=_required_text(entry.get("name"), f"{prefix}.name"),
                slug=_optional_text(entry.get("slug"), f"{prefix}.slug"),
                category=_optional_text(entry.get("category"), f"{prefix}.category"),
                kills=_integer(entry.get("kills"), f"{prefix}.kills"),
                time_in_seconds=_integer(entry.get("timeIn"), f"{prefix}.timeIn"),
                destroy_x_in_y=destroy,
            )
        )
    return result
