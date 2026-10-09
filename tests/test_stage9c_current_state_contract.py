"""Offline admission-concurrency invariants, without database access.

These are *not* a substitute for the isolated PostgreSQL race proof.
"""
from pathlib import Path

from bf4ps.background_service import (
    ACTIVE_SLOTS,
    BACKGROUND_SLOTS_PER_HOUR,
    BOOTSTRAP_SLOTS,
    RECOVERY_SLOTS,
)


def test_frozen_aggregate_and_fairness_shares():
    assert BACKGROUND_SLOTS_PER_HOUR == 1296
    assert ACTIVE_SLOTS + BOOTSTRAP_SLOTS + RECOVERY_SLOTS == BACKGROUND_SLOTS_PER_HOUR


def test_admission_lock_and_usage_query_are_shared():
    source = Path("bf4ps/background_service.py").read_text()
    assert "pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))" in source
    assert "event_type = 'collection_attempt_started'" in source
    assert "status IN ('claimed', 'running')" in source
    assert "e.attempt_number = j.attempt_count" in source
    assert "if usage.total >= BACKGROUND_SLOTS_PER_HOUR:" in source


def test_checkpoint_preserves_hold_and_existing_evidence():
    checkpoint = Path("docs/PROJECT-CURRENT-STATE.md").read_text()
    assert "HOLD / NOT AUTHORIZED" in checkpoint
    assert "406/406 PASS" in checkpoint
    assert "22 checks PASS" in checkpoint
    assert "no concurrency harness execution has yet been claimed" in checkpoint
