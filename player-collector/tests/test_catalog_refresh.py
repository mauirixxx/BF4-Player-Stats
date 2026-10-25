from datetime import datetime, timedelta, timezone
from bf4ps.catalog_refresh import needs_refresh

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def row(age=timedelta(minutes=1), name='AEK', slug='aek', category='rifle'):
    return ('GUID', 42, name, slug, category, NOW-age)


def test_missing_catalog_entry_requires_reconciliation():
    assert needs_refresh(None, name='AEK', slug='aek', category='rifle', observed_at=NOW)


def test_unchanged_recent_catalog_entry_skips_rewrite():
    assert not needs_refresh(row(), name='AEK', slug='aek', category='rifle', observed_at=NOW)


def test_recent_metadata_drift_does_not_trigger_rewrite():
    assert not needs_refresh(row(name='OLD'), name='AEK', slug='aek', category='rifle', observed_at=NOW)


def test_stale_metadata_is_refreshed():
    assert needs_refresh(row(age=timedelta(minutes=16), name='OLD'), name='AEK', slug='aek', category='rifle', observed_at=NOW)


def test_stale_sighting_is_refreshed():
    assert needs_refresh(row(age=timedelta(minutes=16)), name='AEK', slug='aek', category='rifle', observed_at=NOW)