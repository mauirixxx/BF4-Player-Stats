"""Offline T4 recovery guards: no database connection or writes."""
from types import SimpleNamespace as Row
import pytest
from scripts.phase5b_stage9c_t4_recovery_rules import validate_partial_ledger

def job(status="pending", attempts=0, owner=None, sid=1):
    return Row(status=status, attempt_count=attempts, collector_uuid=owner, soldier_id=sid)

def jobs():
    return [job(sid=i) for i in (1, 2, 3)]

def event(host=None, outcome=None):
    return Row(host=host, outcome=outcome)

def test_seed_only_recovery_shape_allowed():
    validate_partial_ledger([], [], [], jobs())

def test_partial_ready_allowed():
    validate_partial_ledger([event("tcou")], [], [], jobs())

def test_partial_done_with_winner_allowed():
    js=jobs()
    js[0]=job("claimed",1,"collector",1)
    validate_partial_ledger([event("tcou"),event("hnl-01")],[event()],
                            [event("tcou","WIN")],js)

@pytest.mark.parametrize("ready,released,done,js", [
    ([event("tcou")]*2, [], [], jobs()),
    ([event("bogus")], [], [], jobs()),
    ([event("tcou","WIN")], [], [], jobs()),
    ([], [event("tcou")], [], jobs()),
    ([], [], [event("tcou","DENIED")], jobs()),
    ([event("tcou")], [event()], [event("kah-01","DENIED")], jobs()),
    ([event("tcou")], [event()], [event("tcou","BOGUS")], jobs()),
    ([event("tcou"),event("hnl-01"),event("kah-01")],[event()],
     [event("tcou","WIN"),event("hnl-01","DENIED"),event("kah-01","DENIED")],jobs()),
    ([],[],[],[job("pending",1,sid=1),job(sid=2),job(sid=3)]),
    ([],[],[],[job("claimed",1,"collector",1),job(sid=2),job(sid=3)]),
    ([event("tcou")],[event()],[event("tcou","WIN")],jobs()),
    ([event("tcou")],[event()],[event("tcou","WIN")],
     [job("claimed",1,"collector",1),job("claimed",1,"other",2),job(sid=3)]),
])
def test_reject_unsafe_recovery_shapes(ready,released,done,js):
    with pytest.raises(ValueError):
        validate_partial_ledger(ready,released,done,js)
