"""Static safety guard until disposable PostgreSQL privilege tests run."""
from pathlib import Path

SQL = Path('migrations/versions/0010_manual_api_function.py').read_text()


def test_function_is_inert_until_dedicated_owner_exists():
    assert 'SECURITY INVOKER' in SQL
    assert 'SECURITY DEFINER' not in SQL
    assert 'REVOKE ALL ON FUNCTION manual_api.request_existing_soldier' in SQL
    assert 'CREATE ROLE' not in SQL
    assert 'CREATE USER' not in SQL


def test_function_restricts_lease_mutations_and_uses_identity():
    assert 'p_persona_id bigint' in SQL
    assert 'p_platform text' in SQL
    assert 'FOR UPDATE' in SQL
    assert "j.status = 'pending'" in SQL
    assert 'j.last_error_at IS NULL' in SQL
    assert 'j.eligible_at <= v_now' in SQL
    assert 'ON CONFLICT (soldier_id,resource) DO NOTHING' in SQL
    assert 'lease_token =' not in SQL
    assert "'up_to_date'::text" in SQL