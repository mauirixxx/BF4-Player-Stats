"""D2-only eight-connection claim race. No HTTP or production access."""
import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from sqlalchemy import create_engine, text
from bf4ps.collection_jobs import claim_next_job, enqueue_job
from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)


def run(url):
    validate_target(url)
    engine = create_engine(url, pool_size=9, max_overflow=0,
                           connect_args={"connect_timeout": 5})
    marker = "synthetic-eight-claim-" + uuid4().hex
    workers = [uuid4() for _ in range(8)]
    sid = None
    try:
        with engine.connect() as conn:
            identity = conn.execute(text(
                "SELECT current_database(),current_user,inet_server_addr(),"
                "pg_is_in_recovery(),current_setting('transaction_read_only')"
            )).one()
            assert (identity[0], identity[1], str(identity[2]), identity[3], identity[4]) == (
                EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off")
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
            assert not any(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                           for table in ("soldiers", "collection_jobs", "collectors", "collection_events"))
            conn.rollback()
        with engine.begin() as conn:
            sid = conn.execute(text("""
                INSERT INTO soldiers (persona_id,platform,current_name,first_seen_at,last_seen_at)
                VALUES (:persona,'pc',:name,now(),now()) RETURNING soldier_id
            """), {"persona": 1600000000 + uuid4().int % 100000000, "name": marker}).scalar_one()
            for i, uid in enumerate(workers):
                conn.execute(text("""
                    INSERT INTO collectors (collector_uuid,collector_name,hostname,lane,egress_key)
                    VALUES (:uid,:name,'tcou','background',:egress)
                """), {"uid": uid, "name": marker + str(i), "egress": "synthetic-" + str(i)})
            jid = enqueue_job(conn, soldier_id=sid, resource="detailed",
                              priority_class="bootstrap", reason=marker)
            conn.execute(text("""
                UPDATE collection_jobs SET last_error_at=now()-interval '2 hours',
                    eligible_at=now()-interval '31 minutes' WHERE job_id=:jid
            """), {"jid": jid})
        for round_index in range(3):
            barrier = Barrier(8)
            def contender(index):
                barrier.wait(timeout=15)
                with engine.begin() as conn:
                    return claim_next_job(conn, collector_uuid=workers[index],
                                          resource="detailed", lane="background",
                                          allowed_soldier_ids=[sid])
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(contender, i) for i in range(8)]
                results = [future.result(timeout=25) for future in futures]
            winners = [j for j in results if j is not None]
            assert len(winners) == 1, results
            winner = winners[0]
            assert winner.job_id == jid and winner.attempt_count == round_index + 1
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT collector_uuid,lease_token,attempt_count,status
                    FROM collection_jobs WHERE job_id=:jid
                """), {"jid": jid}).one()
                assert row.collector_uuid == winner.collector_uuid
                assert row.lease_token == winner.lease_token
                assert row.status == "claimed" and row.attempt_count == round_index + 1
                conn.rollback()
            print(f"PASS: D2 round {round_index+1}: one claim, seven skipped")
            if round_index < 2:
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE collection_jobs SET status='pending',collector_uuid=NULL,
                            lease_token=NULL,claimed_at=NULL,started_at=NULL,
                            lease_expires_at=NULL WHERE job_id=:jid
                    """), {"jid": jid})
    finally:
        try:
            if sid is not None:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM collection_jobs WHERE soldier_id=:sid"), {"sid": sid})
                    conn.execute(text("DELETE FROM soldiers WHERE soldier_id=:sid"), {"sid": sid})
                    conn.execute(text("DELETE FROM collectors WHERE collector_uuid=ANY(:ids)"),
                                 {"ids": workers})
        finally:
            engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required")
    url = os.environ.get("BF4PS_STAGE9C_D2_URL")
    if not url:
        parser.error("BF4PS_STAGE9C_D2_URL required")
    run(url)
