"""D2 isolated migration harness guard tests (no database connection)."""
import pytest

from scripts.phase5b_stage9c_d2_ledger_integration import validate_target


def test_only_dedicated_d2_database_is_accepted():
    validate_target(
        "postgresql+psycopg://bf4ps_stage9c_d2:unused@"
        "mak-db-02.bf4statusbot.com:5432/bf4ps_scratch_stage9c_d2"
    )


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://bf4ps_stage9c_integration:unused@mak-db-02.bf4statusbot.com:5432/bf4ps_scratch_stage9c_integration",
    "postgresql+psycopg://bf4ps_stage9c_d2:unused@mak-db-02.bf4statusbot.com:5432/bf4_serverwatcher",
    "postgresql+psycopg://bf4ps_stage9c_d2:unused@localhost:5432/bf4ps_scratch_stage9c_d2",
    "sqlite:///tmp/unsafe.db",
])
def test_other_targets_refused(url):
    with pytest.raises(RuntimeError, match="REFUSING"):
        validate_target(url)
