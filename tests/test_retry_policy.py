from pathlib import Path

import pytest

from bf4ps.retry_policy import retry_delay_seconds


@pytest.mark.parametrize(
    ("failure_number", "expected_seconds"),
    [
        (1, 15 * 60),
        (2, 60 * 60),
        (3, 6 * 60 * 60),
        (4, 24 * 60 * 60),
        (5, 24 * 60 * 60),
        (100, 24 * 60 * 60),
    ],
)
def test_frozen_retry_backoff(failure_number, expected_seconds):
    assert retry_delay_seconds(failure_number) == expected_seconds


def test_retry_backoff_rejects_nonpositive_failure_numbers():
    with pytest.raises(ValueError):
        retry_delay_seconds(0)


@pytest.mark.parametrize(
    ("path", "resource"),
    [
        ("bf4ps/detailed_collector.py", "detailed"),
        ("bf4ps/weapon_collector.py", "weapons"),
        ("bf4ps/vehicle_collector.py", "vehicles"),
    ],
)
def test_collectors_default_to_persisted_retry_policy(path, resource):
    source = Path(path).read_text()
    assert "retry_after_seconds: int | None = None" in source
    assert "retry_delay_for_failure(" in source
    assert f'resource="{resource}"' in source
    assert "retry_after_seconds=effective_retry_after_seconds" in source


@pytest.mark.parametrize(
    ("path", "resource"),
    [
        ("bf4ps/detailed_persistence.py", "detailed"),
        ("bf4ps/weapon_persistence.py", "weapons"),
        ("bf4ps/vehicle_persistence.py", "vehicles"),
    ],
)
def test_success_resets_resource_failure_debt(path, resource):
    source = Path(path).read_text()
    assert f"{resource}_consecutive_failures = 0" in source
    assert f"{resource}_last_error_class = NULL" in source
    assert f"{resource}_last_error_message = NULL" in source


def test_vehicle_failure_validates_vehicle_resource():
    source = Path("bf4ps/vehicle_failure.py").read_text()
    assert 'if job.resource != "vehicles":' in source
    assert 'if job.resource != "weapons":' not in source
