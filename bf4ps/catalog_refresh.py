"""Bounded shared-equipment catalog metadata refresh policy."""

from datetime import datetime, timedelta

CATALOG_REFRESH_INTERVAL = timedelta(minutes=15)


def needs_refresh(existing, *, name: str, slug: str, category: str, observed_at: datetime) -> bool:
    """Catalog IDs remain stable; refresh metadata changes immediately and sightings periodically.

    Existing is a row: guid, catalog_id, name, slug, category, last_seen_at.
    """
    if existing is None:
        return True
    return (existing[2], existing[3], existing[4]) != (name, slug, category) or (
        existing[5] < observed_at - CATALOG_REFRESH_INTERVAL
    )