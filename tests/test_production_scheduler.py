from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from bf4ps.production_scheduler import classify_source_age, resource_is_eligible


NOW = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc)


def test_source_class_boundaries():
    assert classify_source_age(last_seen_at=NOW - timedelta(hours=24), as_of=NOW) == "active"
    assert classify_source_age(last_seen_at=NOW - timedelta(hours=24, seconds=1), as_of=NOW) == "recent"
    assert classify_source_age(last_seen_at=NOW - timedelta(days=7), as_of=NOW) == "recent"
    assert classify_source_age(last_seen_at=NOW - timedelta(days=7, seconds=1), as_of=NOW) == "inactive"


def test_source_class_rejects_naive_or_future_timestamps():
    with pytest.raises(ValueError):
        classify_source_age(last_seen_at=NOW.replace(tzinfo=None), as_of=NOW)
    with pytest.raises(ValueError):
        classify_source_age(last_seen_at=NOW + timedelta(seconds=1), as_of=NOW)


@pytest.mark.parametrize("resource_state", ["never_attempted", "success", "temporary_failure", "unavailable"])
def test_new_soldier_only_bootstraps_never_attempted_resources(resource_state):
    assert resource_is_eligible(
        state=resource_state,
        next_due_at=None,
        observed_at=NOW,
        source_class="active",
        newly_discovered=True,
    ) is (resource_state == "never_attempted")


def test_active_returning_resource_requires_success_and_due_time():
    assert resource_is_eligible(
        state="success",
        next_due_at=NOW,
        observed_at=NOW,
        source_class="active",
        newly_discovered=False,
    )
    assert not resource_is_eligible(
        state="success",
        next_due_at=NOW + timedelta(seconds=1),
        observed_at=NOW,
        source_class="active",
        newly_discovered=False,
    )
    assert not resource_is_eligible(
        state="success",
        next_due_at=None,
        observed_at=NOW,
        source_class="active",
        newly_discovered=False,
    )
    assert not resource_is_eligible(
        state="temporary_failure",
        next_due_at=NOW - timedelta(hours=1),
        observed_at=NOW,
        source_class="active",
        newly_discovered=False,
    )


@pytest.mark.parametrize("source_class", ["recent", "inactive"])
def test_recent_and_inactive_observations_do_not_create_refresh_debt(source_class):
    assert not resource_is_eligible(
        state="success",
        next_due_at=NOW - timedelta(days=30),
        observed_at=NOW,
        source_class=source_class,
        newly_discovered=False,
    )


def test_success_persistence_stamps_frozen_due_intervals():
    detailed = Path("bf4ps/detailed_persistence.py").read_text()
    weapons = Path("bf4ps/weapon_persistence.py").read_text()
    vehicles = Path("bf4ps/vehicle_persistence.py").read_text()

    assert ":source_fetched_at + interval '24 hours'" in detailed
    assert "detailed_next_due_at = EXCLUDED.detailed_next_due_at" in detailed
    assert ":source_fetched_at + interval '7 days'" in weapons
    assert "weapons_next_due_at = EXCLUDED.weapons_next_due_at" in weapons
    assert ":source_fetched_at + interval '7 days'" in vehicles
    assert "vehicles_next_due_at = EXCLUDED.vehicles_next_due_at" in vehicles


def test_materializer_preserves_existing_queue_authority():
    script = Path("bf4ps/production_scheduler.py").read_text()
    assert "INSERT INTO collection_jobs" in script
    assert "ON CONFLICT (soldier_id, resource) DO NOTHING" in script
    assert "DELETE FROM collection_jobs" not in script
    assert "UPDATE collection_jobs" not in script
    assert 'RETAINED_RESOURCES = ("detailed", "weapons", "vehicles")' in script
