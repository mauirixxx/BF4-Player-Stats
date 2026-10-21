"""Opt-in PostgreSQL integration tests. NEVER points at production.

Run with BF4PS_RANK_TEST_DATABASE_URL=<isolated migrated scratch database URL>
python -m unittest discover -s tests -p test_rank_postgres_integration.py -v
"""
import os
import uuid
import unittest

URL = os.getenv("BF4PS_RANK_TEST_DATABASE_URL")

@unittest.skipUnless(URL, "requires isolated BF4PS_RANK_TEST_DATABASE_URL")
class RankPostgresIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        if make_url(URL).database != "bf4ps_ranking_scratch":
            raise RuntimeError("refusing non-scratch database")
        cls.engine = create_engine(URL, pool_pre_ping=True)
        with cls.engine.connect() as c:
            revision = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != "0018_distributed_rank_queue":
                raise RuntimeError("scratch must be migrated to 0018")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "engine"):
            cls.engine.dispose()

    def test_capacity_claim_and_stale_fence(self):
        from sqlalchemy import text
        from bf4ps.distributed_rank_queue import register, claim, renew, finish
        e = self.engine
        worker1 = register(e, "test-rank-a")
        worker2 = register(e, "test-rank-b")
        item = 900000000 + (uuid.uuid4().int % 100000000)
        key = dict(kind="vehicle", item_id=item, platform="all", metric="kills")
        with e.begin() as c:
            c.execute(text("""INSERT INTO equipment_rank_jobs
                (kind,item_id,platform,metric,next_due_at)
                VALUES (:kind,:item_id,:platform,:metric,clock_timestamp() - interval '1 day')"""), key)
        try:
            with e.begin() as c:
                c.execute(text("UPDATE equipment_rank_capacity SET max_active_builds=1 WHERE id=1"))
                c.execute(text("""UPDATE equipment_rank_jobs SET next_due_at=clock_timestamp()+interval '1 day'
                    WHERE NOT (kind=:kind AND item_id=:item_id AND platform=:platform AND metric=:metric)
                    AND lease_expires_at IS NULL"""), key)
            first = claim(e, worker1)
            self.assertIsNotNone(first)
            self.assertEqual(tuple(first[k] for k in ("kind","item_id","platform","metric")),
                             tuple(key[k] for k in ("kind","item_id","platform","metric")))
            self.assertIsNone(claim(e, worker2), "capacity 1 must deny competing claim")
            self.assertTrue(renew(e, first))
            with e.begin() as c:
                c.execute(text("""UPDATE equipment_rank_jobs
                    SET lease_expires_at=clock_timestamp()-interval '1 second'
                    WHERE kind=:kind AND item_id=:item_id AND platform=:platform AND metric=:metric"""), key)
            self.assertFalse(renew(e, first), "expired worker must not renew")
            self.assertFalse(finish(e, first, True), "expired worker must not finish")
            second = claim(e, worker2)
            self.assertIsNotNone(second)
            self.assertGreater(second["epoch"], first["epoch"])
            self.assertNotEqual(second["token"], first["token"])
            with e.begin() as c:
                stale = c.execute(text("""SELECT 1 FROM equipment_rank_jobs
                    WHERE kind=:kind AND item_id=:item_id AND platform=:platform AND metric=:metric
                    AND claimed_by=:worker AND claim_token=:token AND claim_epoch=:epoch
                    AND lease_expires_at>clock_timestamp() FOR UPDATE"""),
                    {**key, "worker":first["worker_id"], "token":first["token"], "epoch":first["epoch"]}).scalar_one_or_none()
            self.assertIsNone(stale, "stale builder must be denied publication")
            self.assertTrue(finish(e, second, True, refresh_seconds=3600))
        finally:
            with e.begin() as c:
                c.execute(text("""DELETE FROM equipment_rank_jobs
                    WHERE kind=:kind AND item_id=:item_id AND platform=:platform AND metric=:metric"""), key)
                c.execute(text("DELETE FROM equipment_rank_workers WHERE worker_id IN (:a,:b)"), dict(a=worker1,b=worker2))

if __name__ == "__main__":
    unittest.main()
