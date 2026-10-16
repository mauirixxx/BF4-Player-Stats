"""Source contract for the two central production collector exclusion boundaries."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_claim_filters_active_exclusions_before_locking():
    source = (ROOT / 'bf4ps/collection_jobs.py').read_text()
    candidate = source.split('WITH candidate AS (', 1)[1].split('FOR UPDATE SKIP LOCKED', 1)[0]
    assert 'public.player_exclusions' in candidate
    assert 'e.active' in candidate
    assert 'e.persona_id=s.persona_id' in candidate


def test_physical_gate_checks_exclusion_before_authorization():
    source = (ROOT / 'bf4ps/physical_dispatch_gate.py').read_text()
    attempt = source.split('def authorized_http_attempt(', 1)[1]
    assert attempt.index('public.player_exclusions') < attempt.index('permit = authorize_physical_dispatch(')
    assert 'physical HTTP authorization rejected: excluded soldier' in attempt
