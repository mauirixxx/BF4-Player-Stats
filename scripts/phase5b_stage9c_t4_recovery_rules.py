"""Pure fail-closed validation for interrupted T4 fixture recovery.

No SQL, external requests, or side effects. Used before destructive cleanup.
"""
from __future__ import annotations

HOSTS = frozenset(("tcou", "hnl-01", "kah-01"))
READY = "stage9c_t4_ready"
RELEASE = "stage9c_t4_release"
DONE = "stage9c_t4_done"


def validate_partial_ledger(ready, released, done, jobs):
    """Raise ValueError on any unsupported recovery shape."""
    if len(ready) == 3 and len(released) == 1 and len(done) == 3:
        raise ValueError("complete run requires normal cleanup")
    if len(ready) > 3 or len(released) > 1 or len(done) > 3:
        raise ValueError("excess ledger records")
    ready_hosts = [r.host for r in ready]
    done_hosts = [r.host for r in done]
    if len(set(ready_hosts)) != len(ready_hosts) or not set(ready_hosts) <= HOSTS:
        raise ValueError("invalid READY host identities")
    if any(r.outcome is not None for r in ready):
        raise ValueError("READY must not have outcome")
    if any(r.host is not None or r.outcome is not None for r in released):
        raise ValueError("invalid RELEASE fields")
    if len(set(done_hosts)) != len(done_hosts) or not set(done_hosts) <= HOSTS:
        raise ValueError("invalid DONE host identities")
    if any(r.outcome not in ("WIN", "DENIED") for r in done):
        raise ValueError("invalid DONE outcome")
    if done and not released:
        raise ValueError("DONE without RELEASE")
    if not set(done_hosts) <= set(ready_hosts):
        raise ValueError("DONE without READY")
    if sum(r.outcome == "WIN" for r in done) > 1:
        raise ValueError("multiple WIN records")
    if len(jobs) != 3 or len({j.soldier_id for j in jobs}) != 3:
        raise ValueError("invalid job identities")
    if any(j.status not in ("pending", "claimed", "running") for j in jobs):
        raise ValueError("invalid job status")
    if any((j.status == "pending" and (j.attempt_count != 0 or j.collector_uuid is not None))
           or (j.status in ("claimed", "running") and (j.attempt_count != 1 or j.collector_uuid is None))
           for j in jobs):
        raise ValueError("invalid attempt/ownership shape")
    if sum(j.attempt_count for j in jobs) > 1:
        raise ValueError("multiple admitted jobs")
    if not released and any(j.attempt_count for j in jobs):
        raise ValueError("admission before RELEASE")
    if any(r.outcome == "WIN" for r in done) and sum(j.attempt_count for j in jobs) != 1:
        raise ValueError("WIN without admitted job")
    if sum(j.attempt_count for j in jobs) == 1 and done and all(r.outcome == "DENIED" for r in done) and len(done) == 3:
        raise ValueError("three DENIED records with admitted job")
