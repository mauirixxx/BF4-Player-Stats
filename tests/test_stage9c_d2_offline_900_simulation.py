"""Pure offline 900-soldier scheduler-model stress checks."""
import pytest

from scripts.stage9c_d2_offline_900_simulation import SITES, simulate


def test_900_soldiers_12_rounds_three_sites():
    result = simulate()
    assert result["total_claims"] == 10800
    assert result["by_site"] == {site: 3600 for site in SITES}
    assert result["ownership_violations"] == []
    assert len(result["rounds_detail"]) == 12
    assert all(r["completed"] == 900 and
               r["by_site"] == {site: 300 for site in SITES}
               for r in result["rounds_detail"])


@pytest.mark.parametrize("seed", [0, 1, 42, 20261011, 999999])
def test_interleavings_preserve_ownership(seed):
    result = simulate(soldiers=900, rounds=3, seed=seed)
    assert not result["ownership_violations"]
    assert result["by_site"] == {site: 900 for site in SITES}


@pytest.mark.parametrize("soldiers,rounds", [(0, 1), (899, 1), (900, 0), (-3, 1)])
def test_invalid_workload_rejected(soldiers, rounds):
    with pytest.raises(ValueError):
        simulate(soldiers=soldiers, rounds=rounds)
