"""Offline safety checks; no PostgreSQL connection or production writes."""
import importlib.util
from pathlib import Path
import pytest

MODULE = Path(__file__).resolve().parents[1] / 'bf4ps' / 'general_rank_publisher.py'
spec = importlib.util.spec_from_file_location('general_rank_publisher', MODULE)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


@pytest.mark.parametrize('metric,platform', [
    ('kills; DROP TABLE soldiers', 'all'),
    ('kills', 'pc; DROP TABLE soldiers'),
    ('not_a_metric', 'all'),
    ('kills', 'invalid'),
])
def test_invalid_scope_never_reaches_database(metric, platform):
    class NoDatabase:
        def execute(self, *_args, **_kwargs):
            raise AssertionError('Database touched for invalid scope')

    with pytest.raises(ValueError):
        publisher.build_scope(NoDatabase(), metric, platform)


def test_scope_count_and_division_cuts():
    assert len(publisher.METRICS) == 14
    assert len(publisher.PLATFORMS) == 4
    assert publisher.CUTS == (3, 8, 15, 25, 35, 50, 65, 80, 90)


def test_revision_gate_prevents_writes():
    calls = []

    class Result:
        def scalar_one(self):
            return '0025_compact_lookup_fk_idx'

    class Conn:
        def execute(self, statement, params=None):
            calls.append(str(statement))
            return Result()

    with pytest.raises(RuntimeError, match='Expected Alembic 0026'):
        publisher.build_scope(Conn(), 'kills', 'all')
    assert len(calls) == 2
    assert not any('INSERT' in sql for sql in calls)
