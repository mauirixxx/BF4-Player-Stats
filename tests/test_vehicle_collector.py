from pathlib import Path

from bf4ps.battlelog_vehicles import (
    VehicleStatsDecodeError,
    VehicleStatsHTTPError,
    VehicleStatsNormalizationError,
    VehicleStatsTransportError,
)
from bf4ps.vehicle_failure import classify_vehicle_failure


def test_vehicle_failure_classification():
    assert classify_vehicle_failure(VehicleStatsHTTPError(429, "rate")).error_class == "battlelog_throttle"
    assert classify_vehicle_failure(VehicleStatsHTTPError(503, "down")).error_class == "battlelog_http_5xx"
    assert classify_vehicle_failure(VehicleStatsDecodeError("bad")).error_class == "battlelog_decode"
    assert classify_vehicle_failure(VehicleStatsNormalizationError("bad")).error_class == "battlelog_normalization"
    assert classify_vehicle_failure(VehicleStatsTransportError("bad")).error_class == "battlelog_transport"


def test_vehicle_collector_records_attempt_before_fetch():
    source = Path("bf4ps/vehicle_collector.py").read_text(encoding="utf-8")
    assert source.index("_record_vehicle_attempt_started(") < source.index("fetch_vehicle_stats(")
    assert "'vehicles', :lane, 'collection_attempt_started'" in source


def test_vehicle_collector_records_persistence_failure_and_reraises():
    source = Path("bf4ps/vehicle_collector.py").read_text(encoding="utf-8")
    assert "'vehicles', :lane, 'collection_persistence_failure'" in source
    assert "'stage', 'persist_vehicle_success'" in source
    assert "_record_vehicle_persistence_failure(" in source


def test_vehicle_collector_uses_normal_queue_gate_and_bounded_claim():
    source = Path("bf4ps/vehicle_collector.py").read_text(encoding="utf-8")
    assert 'resource="vehicles"' in source
    assert "reserve_request_slot(" in source
    assert "max_total_attempts=max_total_attempts" in source
    assert "attempts_after_event_id=attempts_after_event_id" in source
