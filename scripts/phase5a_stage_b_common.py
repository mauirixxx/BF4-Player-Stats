"""Shared boundaries for Phase 5A Stage B vehicle characterization."""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT
from phase5a_stage_a_common import (
    EXPECTED_DATABASE, EXPECTED_REVISION, FROZEN_UUIDS, HOSTS,
    LEASE_SECONDS, REQUEST_INTERVAL_SECONDS, assert_target,
)

GLOBAL_ATTEMPT_CEILING = 30
RETRY_AFTER_SECONDS = 86400
SOFTWARE_VERSION = "phase5a-stage-b-vehicles"
JOB_REASON = "phase5a_stage_b_vehicles"
PRIORITY_VALUE = 1_000_000
RUN_MARKER_EVENT_TYPE = "phase5a_stage_b_run_started"
RUN_NUMBER = 1
PROBE_EVENT_TYPE = "phase5a_stage_b_vehicle_probe_started"
PROBE_SOLDIER_ID = 15
PROBE_BOUNDARY_EVENT_ID = 2360
PROBE_JOB_ID = 2281
SOLDIER_IDS = tuple(int(row[0]) for row in FROZEN_COHORT)


def current_run_start_event_id(conn) -> int:
    row = conn.execute(text("""
        SELECT event_id
        FROM collection_events
        WHERE event_type=:event_type
          AND metadata->>'run_number'=:run_number
        ORDER BY event_id DESC LIMIT 1
    """), {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": str(RUN_NUMBER)}).one_or_none()
    if row is None:
        raise RuntimeError(f"Phase 5A Stage B run {RUN_NUMBER} marker does not exist")
    return int(row.event_id)
