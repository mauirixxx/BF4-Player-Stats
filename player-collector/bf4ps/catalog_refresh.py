"""Bounded shared-equipment catalog metadata refresh policy."""

from datetime import datetime, timedelta

CATALOG_REFRESH_INTERVAL = timedelta(minutes=15)


def needs_refresh(existing, *, name: str, slug: str, category: str, observed_at: datetime) -> bool:
    """Catalog IDs remain stable; throttle every catalog rewrite, including metadata drift.

    Existing is a row: guid, catalog_id, name, slug, category, last_seen_at.
    """
    if existing is None:
        return True
    # Descriptive metadata may differ across platforms/payloads for one GUID.
    # Updating immediately on every difference makes the same small global
    # catalog oscillate thousands of times per minute. Bound ALL writes.
    return existing[5] < observed_at - CATALOG_REFRESH_INTERVAL