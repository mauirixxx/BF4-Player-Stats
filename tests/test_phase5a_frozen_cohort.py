from collections import Counter
from pathlib import Path

from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT


def test_phase5a_frozen_cohort_shape_is_exact():
    assert len(FROZEN_COHORT) == 30
    assert len({row[0] for row in FROZEN_COHORT}) == 30
    assert Counter(row[3] for row in FROZEN_COHORT) == Counter({'pc': 10, 'ps4': 10, 'xboxone': 10})


def test_phase5a_ignition_preflight_is_zero_request_and_read_only():
    source = Path('scripts/phase5a_multiplatform_weapon_ignition.py').read_text(encoding='utf-8')
    assert 'collect_one_weapon_job' not in source
    assert 'enqueue_job' not in source
    assert 'engine.begin' not in source
    assert 'INSERT ' not in source.upper()
    assert 'UPDATE ' not in source.upper()
    assert 'DELETE ' not in source.upper()
    assert 'KNOWN_HISTORICAL_JOB_ID = 2209' in source
