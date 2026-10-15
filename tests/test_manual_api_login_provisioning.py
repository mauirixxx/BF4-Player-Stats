from pathlib import Path
SQL=Path('deploy/sql/manual_api_create_login.sql').read_text()

def test_login_has_no_direct_table_grants():
    assert 'NOSUPERUSER NOCREATEDB NOCREATEROLE' in SQL
    assert 'NOINHERIT CONNECTION LIMIT 4' in SQL
    assert 'GRANT EXECUTE ON FUNCTION manual_api.request_existing_soldier' in SQL
    assert 'GRANT CONNECT ON DATABASE bf4_playerstats' in SQL
    assert 'GRANT UPDATE ON' not in SQL
    assert 'GRANT INSERT ON' not in SQL
    assert 'PASSWORD ' not in SQL.replace('password with','').replace('passwords.','')