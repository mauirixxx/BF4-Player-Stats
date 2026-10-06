from collections import Counter
from pathlib import Path

from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT


def test_phase5a_frozen_cohort_shape_is_exact():
    assert len(FROZEN_COHORT) == 30
    assert len({row[0] for row in FROZEN_COHORT}) == 30
    assert Counter(row[3] for row in FROZEN_COHORT) == Counter({'pc': 10, 'ps4': 10, 'xboxone': 10})


def test_phase5a_ignition_preflight_is_zero_request_read_only_and_full_contract():
    source = Path('scripts/phase5a_multiplatform_weapon_ignition.py').read_text(encoding='utf-8')
    assert 'collect_one_weapon_job' not in source
    assert 'enqueue_job' not in source
    assert 'engine.begin' not in source
    assert 'INSERT ' not in source.upper()
    assert 'UPDATE ' not in source.upper()
    assert 'DELETE ' not in source.upper()
    assert "'phase3e-hnl-01'" in source
    assert "'phase3e-kah-01'" in source
    assert "'phase3e-tcou'" in source
    assert 'all three required request gates exist' in source
    assert 'no foreign weapon/vehicle/background jobs contaminate ignition' in source
    assert 'KNOWN_HISTORICAL_JOB_ID' not in source
