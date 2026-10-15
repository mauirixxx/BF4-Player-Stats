from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from bf4ps.manual_request_admission import admit_registered_soldier
from bf4ps.manual_request_ledger import Acceptance

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)

class Conn:
    def execute(self, statement, params=None):
        sql = str(statement)
        if 'FROM collection_state' in sql:
            state = {'detailed_last_success_at': NOW-timedelta(minutes=10),
                     'weapons_last_success_at': NOW-timedelta(hours=2),
                     'vehicles_last_success_at': NOW-timedelta(minutes=10),
                     'profile_last_success_at': None}
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: state))
        if 'clock_timestamp()' in sql:
            return SimpleNamespace(scalar_one=lambda: NOW)
        raise AssertionError(sql)


def test_acceptance_promotes_only_missing_and_stale_resources():
    with patch('bf4ps.manual_request_admission.accept_existing_soldier_request',return_value=Acceptance(True,17,0)), \
         patch('bf4ps.manual_request_admission.promote_existing_pending_jobs',return_value=('weapons',)) as promote, \
         patch('bf4ps.manual_request_admission.insert_missing_manual_jobs',return_value=('profile',)) as enqueue:
        result = admit_registered_soldier(Conn(),soldier_id=42)
    assert result.accepted and result.request_id == 17
    assert result.resources_needed == ('weapons','profile')
    assert result.promoted == ('weapons',) and result.created == ('profile',)
    enqueue.assert_called_once()
    promote.assert_called_once_with(promote.call_args.args[0],soldier_id=42,resources=('weapons','profile'))


def test_cooldown_skips_all_queue_work():
    with patch('bf4ps.manual_request_admission.accept_existing_soldier_request',return_value=Acceptance(False,12,1800)), \
         patch('bf4ps.manual_request_admission.promote_existing_pending_jobs') as promote:
        result = admit_registered_soldier(Conn(),soldier_id=42)
    assert not result.accepted and result.retry_after_seconds == 1800
    assert result.resources_needed == ()
    promote.assert_not_called()