"""PostgreSQL-only concurrency regression for physical dispatch admission.

Requires an EMPTY, dedicated disposable database migrated to revision 0007.
Never run against the website, Stage 9C cohort, or production databases.

    BF4PS_DISPATCH_TEST_URL=postgresql+psycopg://.../bf4ps_dispatch_gate_test \\
      pytest -q tests/test_physical_dispatch_postgres.py
"""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import os

import pytest
from sqlalchemy import create_engine, text

from bf4ps.physical_dispatch_gate import (
    PHYSICAL_DISPATCHES_PER_HOUR,
    PhysicalDispatchBudgetExhausted,
    authorize_physical_dispatch,
)

TEST_DB_NAME = "bf4ps_dispatch_gate_test"


def test_simultaneous_last_slot_is_admitted_once():
    url = os.getenv("BF4PS_DISPATCH_TEST_URL")
    if not url:
        pytest.skip("dedicated BF4PS_DISPATCH_TEST_URL not configured")
    engine = create_engine(url, pool_size=4, max_overflow=0, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as conn:
            db = conn.execute(text("SELECT current_database()")).scalar_one()
            if db != TEST_DB_NAME:
                pytest.fail(f"REFUSING: expected disposable database {TEST_DB_NAME}, got {db}")
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != "0007_physical_dispatch_gate":
                pytest.fail(f"REFUSING: expected revision 0007, got {revision}")
            count = conn.execute(text("SELECT COUNT(*) FROM outbound_dispatches")).scalar_one()
            if count:
                pytest.fail("REFUSING: disposable dispatch ledger must be empty")

        # Seed N-1 durable dispatch rows. Never touch real jobs or HTTP.
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO outbound_dispatches (
                    dispatch_id, job_id, attempt_number, request_ordinal,
                    resource, lease_token, collector_uuid, egress_key, lane,
                    payload_fingerprint, admitted_at, phase
                )
                SELECT gen_random_uuid(), i, 1, 1, 'detailed',
                       gen_random_uuid(), gen_random_uuid(), 'test', 'background',
                       'seed', clock_timestamp(), 'admitted'
                FROM generate_series(1, :n) AS i
            """), {"n": PHYSICAL_DISPATCHES_PER_HOUR - 1})

        def attempt(i):
            try:
                with engine.begin() as conn:
                    authorize_physical_dispatch(
                        conn, job_id=10000 + i, attempt_number=1,
                        request_ordinal=1, resource="detailed",
                        lease_token=uuid4(), collector_uuid=uuid4(),
                        egress_key=f"test-{i}", lane="background",
                        payload_fingerprint=f"test-{i}",
                    )
                return "admitted"
            except PhysicalDispatchBudgetExhausted:
                return "denied"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, (1, 2)))
        assert sorted(outcomes) == ["admitted", "denied"]
        with engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM outbound_dispatches")).scalar_one()
            assert total == PHYSICAL_DISPATCHES_PER_HOUR
    finally:
        engine.dispose()
