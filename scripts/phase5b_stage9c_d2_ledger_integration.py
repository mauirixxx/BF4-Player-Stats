"""Stage 9C D2 isolated ledger migration integration; NEVER the shared T4 database.

Requires a separately provisioned, EMPTY database with the exact name and
role below. Does not create/drop databases, start workers, or issue HTTP.
Use only with --execute and BF4PS_STAGE9C_D2_URL explicitly set.
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

EXPECTED_HOST = "mak-db-02.bf4statusbot.com"
EXPECTED_IP = "192.168.10.78"
EXPECTED_DB = "bf4ps_scratch_stage9c_d2"
EXPECTED_USER = "bf4ps_stage9c_d2"
HEAD = "0005_stage9c_dispatch_ledger"
PARENT = "0004_stage9c_supervision_runs"


def validate_target(url: str) -> None:
    parsed = make_url(url)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.host != EXPECTED_HOST
        or parsed.database != EXPECTED_DB
        or parsed.username != EXPECTED_USER
        or parsed.port not in (None, 5432)
    ):
        raise RuntimeError("REFUSING unexpected D2 database target")


def assert_empty(engine) -> None:
    with engine.connect() as conn:
        observed = conn.execute(text(
            "SELECT current_database(),current_user,inet_server_addr(),"
            "pg_is_in_recovery(),current_setting('transaction_read_only')"
        )).one()
        if (observed[0], observed[1], str(observed[2]), observed[3], observed[4]) != (
            EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off"
        ):
            raise RuntimeError("REFUSING D2 connection identity")
        count = conn.execute(text(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f')"
        )).scalar_one()
        if count:
            raise RuntimeError("REFUSING D2 database with existing public objects")


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    previous = os.environ.get("BF4PS_DATABASE_URL")
    try:
        assert_empty(engine)
        os.environ["BF4PS_DATABASE_URL"] = url
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
        command.upgrade(cfg, PARENT)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PARENT
        command.upgrade(cfg, HEAD)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
            assert "outbound_dispatches" in inspect(conn).get_table_names()

        identity = dict(
            dispatch_id=uuid4(), job_id=11, attempt_number=1, resource="weapons",
            lease_token=uuid4(), collector_uuid=uuid4(), egress_key="d2-fake-egress",
            lane="background", payload_fingerprint="fake-payload-digest",
        )
        insert = text(
            "INSERT INTO outbound_dispatches "
            "(dispatch_id,job_id,attempt_number,resource,lease_token,collector_uuid,"
            "egress_key,lane,payload_fingerprint,admitted_at) "
            "VALUES (:dispatch_id,:job_id,:attempt_number,:resource,:lease_token,"
            ":collector_uuid,:egress_key,:lane,:payload_fingerprint,clock_timestamp())"
        )
        with engine.begin() as conn:
            conn.execute(insert, identity)
        try:
            with engine.begin() as conn:
                conn.execute(insert, {**identity, "dispatch_id": uuid4()})
        except IntegrityError:
            pass
        else:
            raise AssertionError("duplicate dispatch identity accepted")

        # Nonempty evidence must block downgrade. The migration transaction
        # rolls back automatically on refusal.
        try:
            command.downgrade(cfg, PARENT)
        except RuntimeError as exc:
            if "REFUSING" not in str(exc):
                raise
        else:
            raise AssertionError("downgrade destroyed durable evidence")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
            assert conn.execute(text("SELECT count(*) FROM outbound_dispatches")).scalar_one() == 1

        with engine.begin() as conn:
            conn.execute(text("DELETE FROM outbound_dispatches WHERE dispatch_id=:id"), {"id": identity["dispatch_id"]})
        command.downgrade(cfg, PARENT)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PARENT
            assert "outbound_dispatches" not in inspect(conn).get_table_names()
        command.upgrade(cfg, HEAD)
        print("PASS: D2 isolated 0004->0005, unique identity, guarded downgrade, 0005 restored")
        print("NOTE: disposable D2 database left at 0005; no T4/production state touched")
    finally:
        if previous is None:
            os.environ.pop("BF4PS_DATABASE_URL", None)
        else:
            os.environ["BF4PS_DATABASE_URL"] = previous
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required; no default database access")
    url = os.environ.get("BF4PS_STAGE9C_D2_URL")
    if not url:
        parser.error("BF4PS_STAGE9C_D2_URL required")
    run(url)
