from pathlib import Path
from bf4ps.phase5b_step7_endurance import (
    COHORT_SIZE, GLOBAL_ATTEMPT_CEILING, INITIAL_JOB_COUNT, SOLDIERS_PER_PLATFORM,
)

SCRIPT=Path("scripts/phase5b_step7_candidate_preflight.py")

def test_step7_frozen_endurance_shape():
    assert SOLDIERS_PER_PLATFORM==432
    assert COHORT_SIZE==1296
    assert INITIAL_JOB_COUNT==3888
    assert GLOBAL_ATTEMPT_CEILING==3888

def test_candidate_preflight_is_read_only_network_free_and_pristine():
    s=SCRIPT.read_text()
    assert "engine.connect()" in s and "engine.begin()" not in s
    assert "INSERT " not in s and "UPDATE " not in s and "DELETE " not in s
    assert "collect_one_" not in s and "fetch_" not in s
    assert "detailed_state='never_attempted'" in s
    assert "weapons_state='never_attempted'" in s
    assert "vehicles_state='never_attempted'" in s
    assert "background queue is not empty" in s
    assert "Battlelog requests: 0" in s
