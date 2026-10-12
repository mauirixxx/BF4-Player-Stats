"""Offline D2 engine lifecycle and fail-closed collector tests."""
from unittest.mock import MagicMock, patch

import pytest

from scripts import stage9c_three_hour_soak_guarded_worker as guarded
from scripts import stage9c_three_hour_soak_supervisor as supervisor


def test_engine_pool_is_bounded_and_pre_ping_enabled(monkeypatch):
    monkeypatch.setenv("BF4PS_STAGE9C_D2_URL", "postgresql+psycopg://test:test@localhost/unused")
    with patch.object(guarded, "create_engine") as factory:
        guarded.soak_engine()
    _, kwargs = factory.call_args
    assert kwargs == {
        "pool_size": 1, "max_overflow": 0,
        "pool_timeout": 5, "pool_pre_ping": True,
    }


def test_standalone_work_disposes_owned_engine(monkeypatch):
    monkeypatch.setattr(guarded.os, "uname", lambda: MagicMock(nodename="tcou"))
    db = MagicMock()
    with patch.object(guarded, "soak_engine", return_value=db), patch.object(
        guarded, "_work_with_engine", side_effect=RuntimeError("database unavailable")
    ):
        with pytest.raises(RuntimeError, match="database unavailable"):
            guarded.work("tcou")
    db.dispose.assert_called_once()


def test_shared_engine_not_disposed_by_work(monkeypatch):
    monkeypatch.setattr(guarded.os, "uname", lambda: MagicMock(nodename="tcou"))
    db = MagicMock()
    with patch.object(guarded, "_work_with_engine", return_value=None) as collector:
        assert guarded.work("tcou", db_engine=db) is None
    collector.assert_called_once_with("tcou", db)
    db.dispose.assert_not_called()


def test_worker_loop_disposes_on_exception(monkeypatch):
    monkeypatch.setattr(supervisor.os, "uname", lambda: MagicMock(nodename="tcou"))
    db = MagicMock()
    with patch.object(supervisor, "soak_engine", return_value=db), patch.object(
        supervisor, "_worker_loop_with_engine", side_effect=ValueError("failure")
    ):
        with pytest.raises(ValueError, match="failure"):
            supervisor.worker_loop("tcou")
    db.dispose.assert_called_once()


def test_hostname_guard_blocks_before_engine(monkeypatch):
    monkeypatch.setattr(guarded.os, "uname", lambda: MagicMock(nodename="other"))
    with patch.object(guarded, "soak_engine") as factory:
        with pytest.raises(RuntimeError, match="hostname mismatch"):
            guarded.work("tcou")
    factory.assert_not_called()


def _db_unavailable():
    from sqlalchemy.exc import OperationalError
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_preflight_recovers_from_transient_connection_error():
    db = MagicMock()
    db.connect.side_effect = [_db_unavailable(), MagicMock()]
    with patch.object(guarded, "preflight", return_value={101}) as check:
        result = guarded.preflight_with_db_retry(db, "tcou", sleep=lambda _: None)
    assert result == {101}
    assert db.connect.call_count == 2
    check.assert_called_once()


def test_preflight_connection_error_is_bounded():
    db = MagicMock()
    db.connect.side_effect = _db_unavailable()
    delays = []
    with pytest.raises(Exception) as exc:
        guarded.preflight_with_db_retry(db, "tcou", sleep=delays.append)
    from sqlalchemy.exc import OperationalError
    assert isinstance(exc.value, OperationalError)
    assert db.connect.call_count == 3
    assert delays == [1, 2]


def test_collector_error_never_retries_http_capable_work():
    db = MagicMock()
    with patch.object(guarded, "preflight_with_db_retry", return_value={101}), patch.object(
        guarded, "collect_one_detailed_job", side_effect=_db_unavailable()
    ) as collect:
        with pytest.raises(Exception):
            guarded._work_with_engine("tcou", db)
    collect.assert_called_once()


def test_safety_block_does_not_retry_preflight():
    db = MagicMock()
    with patch.object(guarded, "preflight", side_effect=RuntimeError("SOAK BLOCK: deadline expired")) as check:
        with pytest.raises(RuntimeError, match="deadline expired"):
            guarded.preflight_with_db_retry(db, "tcou", sleep=lambda _: None)
    check.assert_called_once()


def test_worker_loop_fails_closed_after_ambiguous_database_error():
    db = MagicMock()
    with patch.object(supervisor, "work", side_effect=_db_unavailable()) as collector, patch.object(
        supervisor.time, "sleep"
    ) as sleeper:
        from sqlalchemy.exc import OperationalError
        with pytest.raises(OperationalError):
            supervisor._worker_loop_with_engine("tcou", db)
    collector.assert_called_once_with("tcou", db_engine=db)
    sleeper.assert_not_called()


def test_worker_loop_stops_on_expired_deadline_without_replay():
    db = MagicMock()
    with patch.object(supervisor, "work", side_effect=RuntimeError("SOAK BLOCK: deadline expired")) as collector:
        supervisor._worker_loop_with_engine("tcou", db)
    collector.assert_called_once()


def test_worker_claims_only_its_three_site_soldiers():
    from scripts.stage9c_three_site_live_ignition import COHORT
    from types import SimpleNamespace
    db = MagicMock()
    db.connect.return_value.__enter__.return_value.execute.return_value.all.return_value = [
        (i + 1, persona) for i, (_name, persona, _owner) in enumerate(COHORT)
    ]
    expected = [i + 1 for i, (_name, _persona, owner) in enumerate(COHORT) if owner == "tcou"]
    with patch.object(guarded, "preflight_with_db_retry", return_value=list(range(1, 10))), patch.object(
        guarded, "collect_one_detailed_job", return_value=None
    ) as collect:
        guarded._work_with_engine("tcou", db)
    assert collect.call_args.kwargs["allowed_soldier_ids"] == expected


def test_worker_rejects_incomplete_site_mapping_without_collection():
    db = MagicMock()
    db.connect.return_value.__enter__.return_value.execute.return_value.all.return_value = []
    with patch.object(guarded, "preflight_with_db_retry", return_value=list(range(1, 10))), patch.object(
        guarded, "collect_one_detailed_job"
    ) as collect:
        with pytest.raises(RuntimeError, match="invalid soldier mapping"):
            guarded._work_with_engine("tcou", db)
    collect.assert_not_called()
