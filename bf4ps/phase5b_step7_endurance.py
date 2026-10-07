"""Frozen non-I/O boundaries for Phase 5B Step 7 endurance validation."""
from __future__ import annotations

from datetime import timedelta

from bf4ps.phase5b_step6_cohort import HOSTS, FROZEN_UUIDS

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
REQUEST_INTERVAL_SECONDS = 5.0
LEASE_SECONDS = 120
DURATION = timedelta(hours=3)
GLOBAL_ATTEMPT_CEILING = 3888
SOLDIERS_PER_PLATFORM = 432
COHORT_SIZE = 1296
INITIAL_JOB_COUNT = 3888
SOFTWARE_VERSION = "phase5b-step7-endurance"
JOB_REASON = "phase5b_step7_endurance"
PRIORITY_CLASS = "bootstrap"
PRIORITY_VALUE = 0
RUN_MARKER_EVENT_TYPE = "phase5b_step7_run_started"
LIVE_START_EVENT_TYPE = "phase5b_step7_live_started"
RUN_NUMBER = 1
RESOURCES = ("detailed", "weapons", "vehicles")
PLATFORMS = ("pc", "ps4", "xboxone")
STEP6_SOLDIER_IDS = (15, 16, 17, 105, 106, 107, 93, 94, 95)

assert COHORT_SIZE == SOLDIERS_PER_PLATFORM * len(PLATFORMS)
assert INITIAL_JOB_COUNT == COHORT_SIZE * len(RESOURCES)
