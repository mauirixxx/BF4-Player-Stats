"""Continuous three-node 30-soldier shared-queue test worker.

Never exits merely because the queue is empty or retries are deferred.
SIGINT/SIGTERM stop it gracefully. Throttle signals stop external requests.
"""
import os
import signal
import time
from uuid import uuid5, NAMESPACE_DNS

from sqlalchemy import create_engine, text
from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import CollectorIdentity
from scripts.bf4ps_production_collector import collect_one, describe_result
from scripts.phase4c_cohort import PHASE4C_COHORT
from bf4ps.production_hosts import RESOURCES

STOP = False


def request_stop(*_args):
    global STOP
    STOP = True


def main():
    node = os.uname().nodename.split('.')[0]
    assert node in ('tcou', 'kah-01', 'hnl-01')
    engine = create_engine(os.environ['BF4PS_DATABASE_URL'], pool_pre_ping=True)
    ps = [p for plat in ('pc', 'ps4', 'xboxone')
          for _, p, _, _ in [r for r in PHASE4C_COHORT if r[3] == plat][:10]]
    ident = CollectorIdentity(
        uuid5(NAMESPACE_DNS, 'four-resource-30-20261012:' + node),
        'four-resource-30-20261012:' + node, node,
        'four-resource-30-20261012:' + node, 'background')
    with engine.begin() as conn:
        assert conn.execute(text('select current_database()')).scalar_one() == 'bf4ps_scratch_stage9c_d3'
        ids = [r[0] for r in conn.execute(
            text('select soldier_id from soldiers where persona_id=any(:p)'), {'p': ps}).all()]
        assert len(ids) == 30
        register_collector(conn, identity=ident, software_version='four-resource-30-continuous')
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    print('START continuous', node, 'soldiers', len(ids), flush=True)
    resource_index = 0
    next_heartbeat = 0.0
    try:
        while not STOP:
            now = time.monotonic()
            if now >= next_heartbeat:
                with engine.begin() as conn:
                    control = heartbeat_collector(
                        conn, collector_uuid=ident.collector_uuid,
                        software_version='four-resource-30-continuous')
                next_heartbeat = now + 15.0
                if not control.enabled:
                    print('DISABLED; stopping', node, flush=True)
                    break
            if control.drained:
                time.sleep(0.5)
                continue
            resource = RESOURCES[resource_index]
            resource_index = (resource_index + 1) % len(RESOURCES)
            result = collect_one(engine, ident, resource,
                                 allowed_soldier_ids=ids, max_total_attempts=300)
            if result is None:
                time.sleep(0.5)
                continue
            message, throttle = describe_result(resource, result)
            print(node, message, flush=True)
            if throttle:
                print('THROTTLE STOP', node, flush=True)
                break
    finally:
        try:
            with engine.begin() as conn:
                stop_collector(conn, collector_uuid=ident.collector_uuid)
        finally:
            engine.dispose()
    print('STOPPED', node, flush=True)


if __name__ == '__main__':
    main()
