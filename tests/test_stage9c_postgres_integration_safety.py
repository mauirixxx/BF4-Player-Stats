"""Offline refusal tests: never connect to PostgreSQL."""
import pytest

from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://x:y@localhost/bf4_playerstats_test",
    "postgresql+psycopg://x:y@localhost/bf4_playerstats",
    "postgresql+psycopg://x:y@localhost/anything",
    "sqlite:///tmp_stage9c_integration",
])
def test_rejects_non_disposable_targets(url):
    with pytest.raises(RuntimeError, match="REFUSING"):
        refuse_unsafe_target(url)


def test_accepts_only_named_disposable_database():
    assert refuse_unsafe_target(
        "postgresql+psycopg://x:y@localhost/bf4ps_scratch_stage9c_integration"
    ) == "bf4ps_scratch_stage9c_integration"
