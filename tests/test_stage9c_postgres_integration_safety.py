"""Offline target refusal tests: no PostgreSQL connection is made."""
import pytest

from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

GOOD = "postgresql+psycopg://bf4ps_stage9c_integration:secret@mak-db-02.bf4statusbot.com/bf4ps_scratch_stage9c_integration"


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://x:y@localhost/bf4_playerstats_test",
    "postgresql+psycopg://x:y@localhost/bf4_playerstats",
    "postgresql+psycopg://x:y@localhost/anything",
    "sqlite:///tmp_stage9c_integration",
    GOOD.replace("bf4ps_scratch_stage9c_integration", "bf4_playerstats_test"),
    GOOD.replace("mak-db-02.bf4statusbot.com", "localhost"),
    GOOD.replace("bf4ps_stage9c_integration:secret", "postgres:secret"),
    GOOD.replace("mak-db-02.bf4statusbot.com/", "mak-db-02.bf4statusbot.com:5433/"),
])
def test_rejects_non_disposable_targets(url):
    with pytest.raises(RuntimeError, match="REFUSING"):
        refuse_unsafe_target(url)


def test_accepts_only_exact_disposable_target():
    assert refuse_unsafe_target(GOOD) == "bf4ps_scratch_stage9c_integration"
