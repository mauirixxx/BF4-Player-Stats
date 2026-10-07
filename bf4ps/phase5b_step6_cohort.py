"""Frozen non-I/O boundaries for Phase 5B Step 6 bounded live validation."""

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
REQUEST_INTERVAL_SECONDS = 5.0
LEASE_SECONDS = 120
GLOBAL_ATTEMPT_CEILING = 27
SOFTWARE_VERSION = "phase5b-step6-bounded-live"
JOB_REASON = "phase5b_step6_bounded_live"
PRIORITY_VALUE = 0
RUN_MARKER_EVENT_TYPE = "phase5b_step6_run_started"
RUN_NUMBER = 1
RESOURCES = ("detailed", "weapons", "vehicles")

COHORT = (
    (15, 513446234, "jdisa35w", "pc"),
    (16, 759417780, "WT_Stall", "pc"),
    (17, 794963302, "Bbus_A_Nutt", "pc"),
    (105, 232243443, "Mike4doz", "ps4"),
    (106, 319195613, "Xayn2011", "ps4"),
    (107, 350700411, "Midnighttoker760", "ps4"),
    (93, 294684832, "morelock202", "xboxone"),
    (94, 368219573, "GEARHEAD 7432", "xboxone"),
    (95, 372766646, "H Stiglitz6860", "xboxone"),
)
SOLDIER_IDS = tuple(row[0] for row in COHORT)
