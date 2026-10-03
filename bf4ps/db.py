from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from bf4ps.config import database_url


def make_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)
