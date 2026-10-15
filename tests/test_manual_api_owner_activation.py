from pathlib import Path
SQL=Path('deploy/sql/manual_api_activate_owner.sql').read_text()

def test_owner_is_nonlogin_and_function_is_definer():
    assert 'NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION' in SQL
    assert 'SECURITY DEFINER' in SQL
    assert 'OWNER TO bf4ps_manual_function_owner' in SQL
    assert 'REVOKE ALL ON FUNCTION' in SQL
    assert 'BEGIN;' in SQL and 'COMMIT;' in SQL

def test_no_public_api_login_or_stats_table_grants():
    assert 'CREATE USER' not in SQL
    assert 'CREATE ROLE bf4ps_manual_api ' not in SQL
    assert 'detailed_stats_current' not in SQL
    assert 'GRANT DELETE' not in SQL