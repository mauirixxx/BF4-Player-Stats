from uuid import uuid4

import pytest

from bf4ps.collector_runtime import CollectorControl, register_collector
from bf4ps.detailed_collector import CollectorIdentity


def identity(**overrides):
    values = {
        "collector_uuid": uuid4(),
        "collector_name": "tcou-phase2",
        "hostname": "tcou",
        "egress_key": "tcou-phase2",
        "lane": "background",
    }
    values.update(overrides)
    return CollectorIdentity(**values)


def test_control_may_claim_only_when_enabled_and_undrained():
    assert CollectorControl(True, False).may_claim is True
    assert CollectorControl(True, True).may_claim is False
    assert CollectorControl(False, False).may_claim is False
    assert CollectorControl(False, True).may_claim is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("collector_name", "  ", "collector_name must be non-empty"),
        ("hostname", "", "hostname must be non-empty"),
        ("egress_key", " ", "egress_key must be non-empty"),
        ("lane", "bogus", "collector lane must be background or interactive"),
    ],
)
def test_registration_rejects_invalid_identity_before_database_use(field, value, message):
    with pytest.raises(ValueError, match=message):
        register_collector(None, identity=identity(**{field: value}))  # type: ignore[arg-type]
