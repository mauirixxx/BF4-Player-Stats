from pathlib import Path

def test_stage_c_report_is_read_only_and_combines_exact_run_boundaries():
    s=Path("scripts/phase5a_stage_c_report.py").read_text()
    assert "database writes: 0" in s
    assert "Battlelog requests: 0" in s
    assert "stage_a_boundary" in s and "stage_b_boundary" in s
    assert "collection_attempt_started" in s

def test_stage_c_report_does_not_promote_reconnaissance_to_measured_bytes():
    s=Path("scripts/phase5a_stage_c_report.py").read_text()
    assert "do not add reconnaissance detailed payload estimates" in s
    assert "Phase 5A measured only weapons + vehicles" in s

def test_stage_c_report_preserves_three_resource_production_shape():
    s=Path("scripts/phase5a_stage_c_report.py").read_text()
    assert "detailed + weapons + vehicles = 3 requests per soldier" in s
    assert "measured requests per completed soldier" in s

def test_stage_c_report_calls_out_missing_catalog_growth_baseline():
    s=Path("scripts/phase5a_stage_c_report.py").read_text()
    assert "catalog growth: NOT DERIVABLE" in s
    assert "weapon_catalog" in s and "vehicle_catalog" in s
