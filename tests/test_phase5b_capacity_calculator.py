from pathlib import Path

SCRIPT = Path("scripts/phase5b_capacity_calculator.py").read_text()


def test_capacity_calculator_has_no_database_or_network_runtime():
    assert "make_engine" not in SCRIPT
    assert "sqlalchemy" not in SCRIPT.lower()
    assert "requests." not in SCRIPT.lower()
    assert "database access: 0" in SCRIPT
    assert "Battlelog requests: 0" in SCRIPT


def test_capacity_uses_accepted_phase5a_means_and_three_egress_gate():
    assert "EGRESSES = 3" in SCRIPT
    assert "SECONDS_PER_REQUEST_PER_EGRESS = 5.0" in SCRIPT
    assert "WEAPON_BYTES_MEAN = 585850.3" in SCRIPT
    assert "VEHICLE_BYTES_MEAN = 452844.3" in SCRIPT


def test_capacity_population_matches_accepted_census():
    assert '"hot_lt_1h": 3939' in SCRIPT
    assert '"warm_1h_24h": 7844 + 13114' in SCRIPT
    assert '"recent_1d_7d": 47936' in SCRIPT
    assert '"cold_7d_plus": 80558 + 34973' in SCRIPT


def test_candidates_are_explicitly_not_policy():
    assert "No candidate above is authorized production policy." in SCRIPT
    assert "NOT proven gameplay activity" in SCRIPT
    assert "detailed response bytes: UNKNOWN / not included" in SCRIPT
