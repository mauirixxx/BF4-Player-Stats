from datetime import datetime, timezone
from types import SimpleNamespace

from bf4ps.discovery import AliasRow, import_aliases


class GuardedDestination:
    def __init__(self, excluded):
        self.excluded = excluded
        self.calls = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        assert 'public.player_exclusions' in sql, 'excluded identity must not reach any writes'
        assert params == {'platform': 'pc', 'persona_id': 1007062617638}
        return SimpleNamespace(scalar_one=lambda: self.excluded)


def test_excluded_alias_does_not_mutate_destination():
    conn = GuardedDestination(excluded=True)
    alias = AliasRow(1, 'PC', 1007062617638, 'DayWasRuined',
                     datetime.now(timezone.utc), datetime.now(timezone.utc))
    assert import_aliases(conn, [alias], materialize_production_jobs=True) is None
    assert len(conn.calls) == 1
