from unittest.mock import Mock, MagicMock, patch
from bf4ps.manual_add_soldier import add_verified_soldier


def test_verification_precedes_database_write():
    engine = MagicMock()
    verified = object()
    engine.begin.return_value.__enter__.return_value = conn = Mock()
    with patch('bf4ps.manual_add_soldier.fetch_verified_soldier', return_value=verified) as fetch, patch('bf4ps.manual_add_soldier.insert_verified_manual_soldier', return_value=(12, 'accepted')) as insert:
        result = add_verified_soldier(engine, 'url', lambda: None)
    assert result == (12, 'accepted')
    fetch.assert_called_once()
    insert.assert_called_once_with(conn, url='url', verified=verified)


def test_failed_verification_never_opens_database_transaction():
    engine = Mock()
    with patch('bf4ps.manual_add_soldier.fetch_verified_soldier', side_effect=ValueError('invalid')):
        try:
            add_verified_soldier(engine, 'url', lambda: None)
        except ValueError:
            pass
        else:
            raise AssertionError('verification must fail')
    engine.begin.assert_not_called()
