from unittest.mock import Mock, patch
import pytest

from bf4ps.manual_verified_ingestion import VerifiedSoldier, insert_verified_manual_soldier

URL = "https://battlelog.battlefield.com/bf4/soldier/example/stats/876543210/pc/"


def test_rejects_unverified_url_identity_without_database_access():
    conn = Mock()
    with pytest.raises(ValueError, match="mismatch"):
        insert_verified_manual_soldier(conn, url=URL,
            verified=VerifiedSoldier(876543211, "pc", "example"))
    conn.execute.assert_not_called()


def test_rejects_empty_verified_name():
    conn = Mock()
    with pytest.raises(ValueError, match="mismatch"):
        insert_verified_manual_soldier(conn, url=URL,
            verified=VerifiedSoldier(876543210, "pc", "  "))
    conn.execute.assert_not_called()


def test_verified_ingestion_records_manual_source_and_queues_add():
    conn = Mock()
    conn.execute.return_value.scalar_one.return_value = 42
    admission = Mock(accepted=True)
    with patch("bf4ps.manual_verified_ingestion.admit_registered_soldier", return_value=admission) as admit:
        soldier_id, result = insert_verified_manual_soldier(
            conn, url=URL, verified=VerifiedSoldier(876543210, "pc", "Verified Name"))
    assert soldier_id == 42 and result is admission
    assert conn.execute.call_count == 4
    sql = [str(call.args[0]) for call in conn.execute.call_args_list]
    assert "INSERT INTO soldiers" in sql[0]
    assert "INSERT INTO soldier_sources" in sql[1]
    assert "INSERT INTO soldier_names" in sql[2]
    assert "INSERT INTO collection_state" in sql[3]
    assert conn.execute.call_args_list[1].args[1] == {"soldier_id": 42}
    admit.assert_called_once_with(conn, soldier_id=42, kind="add")
