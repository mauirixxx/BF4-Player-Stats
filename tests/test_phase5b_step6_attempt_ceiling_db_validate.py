from pathlib import Path


SCRIPT = Path("scripts/phase5b_step6_attempt_ceiling_db_validate.py")


def test_step6_attempt_ceiling_harness_models_real_attempt_identity():
    source = SCRIPT.read_text()
    assert "RETURNING job_id" in source
    assert "(job_id, soldier_id, resource, lane, event_type, attempt_number)" in source
    assert '"job_id": job_ids[resource]' in source
    assert "GROUP BY job_id, attempt_number" in source
    assert "assert durable_count == 2" in source


def test_step6_attempt_ceiling_harness_is_network_free_and_rolls_back():
    source = SCRIPT.read_text()
    assert "fetch_detailed_stats" not in source
    assert "fetch_weapon_stats" not in source
    assert "fetch_vehicle_stats" not in source
    assert "tx.rollback()" in source
    assert "Battlelog requests: 0" in source
