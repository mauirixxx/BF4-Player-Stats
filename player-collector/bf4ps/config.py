from __future__ import annotations

import os


def database_url() -> str:
    """Return the BF4PS PostgreSQL URL without embedding production credentials in source."""
    value = os.environ.get("BF4PS_DATABASE_URL")
    if not value:
        raise RuntimeError("BF4PS_DATABASE_URL is required")
    return value
