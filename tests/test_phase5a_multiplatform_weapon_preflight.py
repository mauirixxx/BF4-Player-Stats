from pathlib import Path


def test_phase5a_multiplatform_preflight_is_read_only_and_balanced():
    source = Path("scripts/phase5a_multiplatform_weapon_preflight.py").read_text(encoding="utf-8")

    assert 'PLATFORMS = ("pc", "ps4", "xboxone")' in source
    assert "PER_PLATFORM = 10" in source
    assert "selected cohort has no existing weapon/vehicle jobs" in source
    assert "no existing weapon/vehicle jobs contaminate preflight" not in source
    assert "soldier_id IN :soldier_ids" in source
    assert "enqueue_job" not in source
    assert "collect_one_weapon_job" not in source
    assert "engine.begin" not in source
    assert "INSERT " not in source.upper()
    assert "UPDATE " not in source.upper()
    assert "DELETE " not in source.upper()
