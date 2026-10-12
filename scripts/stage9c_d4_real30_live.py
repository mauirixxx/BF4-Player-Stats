"""Bounded D4 real30 live runner. Never runs HTTP without --execute.

One node runs only its frozen 10-soldier partition, at most 30 first
attempts, and stops on any failure. All collectors share a database-backed
403/429 pre-HTTP stop gate. Existing in-flight requests cannot be cancelled.
"""
from __future__ import annotations
import argparse
import json
import os
from uuid import NAMESPACE_DNS, uuid5

from sqlalchemy import text

from scripts.stage9c_d4_real30_queue import (
    DB, NODES, RESOURCES, RUN, cohort, engine, guard, verify,
)
from bf4ps.stage9c_d4_http_stop import assert_no_rate_block
from bf4ps import detailed_collector, weapon_collector, vehicle_collector

COLLECTORS = {
    "detailed": (detailed_collector.CollectorIdentity,
                 detailed_collector.collect_one_detailed_job,
                 detailed_collector.CollectedJob),
    "weapons": (weapon_collector.CollectorIdentity,
                weapon_collector.collect_one_weapon_job,
                weapon_collector.CollectedWeaponJob),
    "vehicles": (vehicle_collector.CollectorIdentity,
                 vehicle_collector.collect_one_vehicle_job,
                 vehicle_collector.CollectedVehicleJob),
}

def preflight(e, node):
    if os.uname().nodename != node:
        raise RuntimeError("D4 worker hostname mismatch")
    with e.connect() as conn:
        ids = guard(conn)
        selected = [r for r in cohort() if r["site"] == node]
        if len(selected) != 10:
            raise RuntimeError("wrong site partition")
        soldier_ids = sorted(ids[(r["persona_id"], r["platform"])] for r in selected)
        jobs = conn.execute(text("""
            SELECT soldier_id,resource,status,attempt_count,reason
            FROM collection_jobs
        """)).all()
        if len(jobs) != 90 or any(
            status != "pending" or attempts != 0 or reason != RUN
            for _,_,status,attempts,reason in jobs
        ):
            raise RuntimeError("D4 queue no longer at untouched launch baseline")
        if conn.execute(text("SELECT count(*) FROM collection_events")).scalar_one():
            raise RuntimeError("D4 collection events already exist")
        assert_no_rate_block(conn)
    print(json.dumps({"node":node,"soldiers":len(soldier_ids),"jobs":30,
                      "database":DB,"http_authorized":False,
                      "platforms":{p:sum(r["platform"]==p for r in selected)
                                   for p in ("pc","ps4","xboxone")}},sort_keys=True),flush=True)
    return soldier_ids


def run(e, node):
    if os.uname().nodename != node:
        raise RuntimeError("hostname mismatch")
    with e.connect() as conn:
        ids = guard(conn)
        selected = [r for r in cohort() if r["site"] == node]
        soldier_ids = sorted(ids[(r["persona_id"], r["platform"])] for r in selected)
        if len(soldier_ids) != 10:
            raise RuntimeError("invalid site cohort")
        jobs = conn.execute(text("""
            SELECT soldier_id,resource,attempt_count,status,reason
            FROM collection_jobs WHERE soldier_id = ANY(:ids)
        """),{"ids":soldier_ids}).all()
        if len(jobs) != 30 or any(attempts or status!="pending" or reason!=RUN
                                  for _,_,attempts,status,reason in jobs):
            raise RuntimeError("site jobs not at fresh first-attempt baseline")
        assert_no_rate_block(conn)

    for resource in RESOURCES:
        cls, collect, success_type = COLLECTORS[resource]
        identity = cls(
            collector_uuid=uuid5(NAMESPACE_DNS,RUN+":"+node),
            collector_name=RUN+":"+node,
            hostname=node,egress_key=RUN+":"+node,lane="background",
        )
        for i in range(10):
            with e.connect() as conn:
                assert_no_rate_block(conn)
            result = collect(
                e, identity=identity, request_interval_seconds=10.0,
                allowed_soldier_ids=soldier_ids,
                max_total_attempts=90,
                attempts_after_event_id=0,
                attempt_ceiling_resources=RESOURCES,
                enforce_production_budget=True,
                pre_http_admission=assert_no_rate_block,
                lease_seconds=120, timeout_seconds=30.0,
                retry_after_seconds=3600,
            )
            print(f"D4 node={node} resource={resource} slot={i+1}/10 result={result!r}",flush=True)
            if not isinstance(result,success_type):
                raise RuntimeError("D4 STOP: non-success, no automatic retries")
    print(f"D4 NODE COMPLETE {node}",flush=True)


def status(e):
    with e.connect() as conn:
        guard(conn)
        rows = conn.execute(text("""
            SELECT resource,status,count(*) FROM collection_jobs
            GROUP BY resource,status ORDER BY resource,status
        """)).all()
        errors = conn.execute(text("""
            SELECT event_id,resource,http_status,error_class
            FROM collection_events WHERE event_type='collection_failure'
            ORDER BY event_id DESC LIMIT 10
        """)).all()
        attempts = conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE event_type='collection_attempt_started'
        """)).scalar_one()
        print(json.dumps({"jobs":[list(r) for r in rows],
                          "physical_attempts":attempts,
                          "recent_failures":[list(r) for r in errors]},sort_keys=True))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("preflight","run","status"))
    p.add_argument("--node",choices=NODES)
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    e=engine()
    if a.command=="status":status(e)
    elif a.command=="preflight":
        if not a.node:p.error("--node required")
        preflight(e,a.node)
    else:
        if not a.node or not a.execute:p.error("run requires --node and --execute")
        run(e,a.node)

if __name__=="__main__":main()
