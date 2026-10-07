from bf4ps.phase5b_step6_cohort import (
    COHORT, EXPECTED_DATABASE, EXPECTED_REVISION, GLOBAL_ATTEMPT_CEILING,
    REQUEST_INTERVAL_SECONDS, RESOURCES, SOLDIER_IDS,
)


def test_step6_cohort_is_small_multiplatform_and_exactly_bounded():
    assert EXPECTED_DATABASE == "bf4_playerstats_test"
    assert EXPECTED_REVISION == "0003_request_gates"
    assert REQUEST_INTERVAL_SECONDS == 5.0
    assert len(COHORT) == 9
    assert len(SOLDIER_IDS) == 9
    assert len(set(SOLDIER_IDS)) == 9
    assert RESOURCES == ("detailed", "weapons", "vehicles")
    assert GLOBAL_ATTEMPT_CEILING == len(COHORT) * len(RESOURCES) == 27
    platforms = [row[3] for row in COHORT]
    assert platforms.count("pc") == 3
    assert platforms.count("ps4") == 3
    assert platforms.count("xboxone") == 3
