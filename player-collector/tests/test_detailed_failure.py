from bf4ps.battlelog_detailed import (
    DetailedStatsDecodeError,
    DetailedStatsHTTPError,
    DetailedStatsNormalizationError,
    DetailedStatsTransportError,
    UnsupportedPlatformError,
)
from bf4ps.detailed_failure import classify_detailed_failure


def test_403_is_classified_as_throttle():
    failure = classify_detailed_failure(DetailedStatsHTTPError(403, "forbidden"))
    assert failure.error_class == "battlelog_throttle"
    assert failure.http_status == 403


def test_429_is_classified_as_throttle():
    failure = classify_detailed_failure(DetailedStatsHTTPError(429, "too many requests"))
    assert failure.error_class == "battlelog_throttle"
    assert failure.http_status == 429


def test_5xx_is_classified_as_transient_http():
    failure = classify_detailed_failure(DetailedStatsHTTPError(503, "unavailable"))
    assert failure.error_class == "battlelog_http_5xx"
    assert failure.http_status == 503


def test_generic_http_is_not_guessed_terminal():
    failure = classify_detailed_failure(DetailedStatsHTTPError(404, "not found"))
    assert failure.error_class == "battlelog_http"
    assert failure.http_status == 404


def test_transport_decode_and_normalization_are_distinct():
    assert classify_detailed_failure(DetailedStatsTransportError("timeout")).error_class == "battlelog_transport"
    assert classify_detailed_failure(DetailedStatsDecodeError("bad json")).error_class == "battlelog_decode"
    assert classify_detailed_failure(DetailedStatsNormalizationError("bad schema")).error_class == "battlelog_normalization"


def test_unsupported_platform_and_unknown_internal_are_distinct():
    assert classify_detailed_failure(UnsupportedPlatformError("wat")).error_class == "bf4ps_unsupported_platform"
    assert classify_detailed_failure(RuntimeError("boom")).error_class == "bf4ps_internal"
