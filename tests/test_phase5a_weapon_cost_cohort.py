from pathlib import Path


def test_phase5a_weapon_cost_cohort_uses_requested_cohort_as_durable_ceiling():
    source = Path("scripts/phase5a_weapon_cost_cohort.py").read_text(encoding="utf-8")

    assert "max_total_attempts=cohort_size" in source
    assert "max_total_attempts=1" not in source
