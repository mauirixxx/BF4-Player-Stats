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
