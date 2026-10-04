"""Phase 2 bounded single-node collector runtime.

This is intentionally a conservative validation runtime, not final service
packaging.  It combines the already-proven feeder, collector registry/control,
fenced single-job collector, and PostgreSQL request gate behind explicit hard
execution boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic, sleep

from sqlalchemy.engine import Engine

from bf4ps.bounded_feeder import FeederResult, replenish_detailed_bootstrap
from bf4ps.collector_runtime import (
    CollectorControl,
    heartbeat_collector,
    register_collector,
    stop_collector,
)
from bf4ps.detailed_collector import (
    CollectedJob,
    CollectorIdentity,
    FailedJob,
    collect_one_detailed_job,
)


@dataclass(frozen=True)
class SingleNodeRuntimeConfig:
    target_depth: int
    max_soldier_id: int
    max_jobs: int
    request_interval_seconds: float
    feeder_interval_seconds: float = 5.0
    heartbeat_interval_seconds: float = 15.0
    idle_sleep_seconds: float = 1.0
    lease_seconds: int = 120
    timeout_seconds: float = 15.0
    retry_after_seconds: int = 300
    software_version: str | None = None


@dataclass(frozen=True)
class SingleNodeRuntimeResult:
    jobs_attempted: int
    jobs_succeeded: int
    jobs_failed: int
    feeder_passes: int
    jobs_materialized: int
    stopped_by_control: bool


def _validate_config(config: SingleNodeRuntimeConfig) -> None:
    if config.target_depth <= 0:
        raise ValueError("target_depth must be positive")
    if config.max_soldier_id <= 0:
        raise ValueError("max_soldier_id must be positive")
    if config.max_jobs <= 0:
        raise ValueError("max_jobs must be positive")
    if config.request_interval_seconds < 0:
        raise ValueError("request_interval_seconds must be non-negative")
    if config.feeder_interval_seconds <= 0:
        raise ValueError("feeder_interval_seconds must be positive")
    if config.heartbeat_interval_seconds <= 0:
        raise ValueError("heartbeat_interval_seconds must be positive")
    if config.idle_sleep_seconds < 0:
        raise ValueError("idle_sleep_seconds must be non-negative")
    if config.lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    if config.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if config.retry_after_seconds < 0:
        raise ValueError("retry_after_seconds must be non-negative")


def _register(
    engine: Engine,
    identity: CollectorIdentity,
    config: SingleNodeRuntimeConfig,
) -> CollectorControl:
    with engine.begin() as conn:
        return register_collector(
            conn,
            identity=identity,
            software_version=config.software_version,
        )


def _heartbeat(
    engine: Engine,
    identity: CollectorIdentity,
    config: SingleNodeRuntimeConfig,
) -> CollectorControl:
    with engine.begin() as conn:
        return heartbeat_collector(
            conn,
            collector_uuid=identity.collector_uuid,
            software_version=config.software_version,
        )


def _feed(engine: Engine, config: SingleNodeRuntimeConfig) -> FeederResult:
    with engine.begin() as conn:
        return replenish_detailed_bootstrap(
            conn,
            target_depth=config.target_depth,
            max_soldier_id=config.max_soldier_id,
        )


def run_bounded_single_node(
    engine: Engine,
    *,
    identity: CollectorIdentity,
    config: SingleNodeRuntimeConfig,
) -> SingleNodeRuntimeResult:
    """Run one bounded Phase 2 automatic-work validation loop.

    ``max_jobs`` is a hard process-level ceiling on collection attempts.  The
    function never preclaims work; each call to ``collect_one_detailed_job``
    owns at most one queue row and the existing request gate remains mandatory
    inside that collector path.

    Operator ``enabled``/``drained`` state is checked before feeder
    materialization and before every new claim.  A quiescent operator control
    state ends this bounded validation invocation rather than waiting forever.
    """
    _validate_config(config)

    attempted = 0
    succeeded = 0
    failed = 0
    feeder_passes = 0
    materialized = 0
    stopped_by_control = False

    control = _register(engine, identity, config)
    last_heartbeat = monotonic()
    last_feeder: float | None = None

    try:
        while attempted < config.max_jobs:
            now = monotonic()
            if now - last_heartbeat >= config.heartbeat_interval_seconds:
                control = _heartbeat(engine, identity, config)
                last_heartbeat = now
            else:
                # Control state is deliberately refreshed every loop even when
                # a heartbeat write is not yet due.  For the first single-node
                # runtime, correctness/operator responsiveness matters more
                # than shaving one tiny SELECT/UPDATE transaction.
                control = _heartbeat(engine, identity, config)
                last_heartbeat = now

            if not control.may_claim:
                stopped_by_control = True
                break

            now = monotonic()
            if last_feeder is None or now - last_feeder >= config.feeder_interval_seconds:
                feed = _feed(engine, config)
                feeder_passes += 1
                materialized += feed.created
                last_feeder = now

            # Re-read operator control immediately before entering the claim
            # path so a drain/disable issued during feeder work blocks the next
            # claim.  Queue ownership itself remains PostgreSQL-fenced.
            control = _heartbeat(engine, identity, config)
            last_heartbeat = monotonic()
            if not control.may_claim:
                stopped_by_control = True
                break

            outcome = collect_one_detailed_job(
                engine,
                identity=identity,
                request_interval_seconds=config.request_interval_seconds,
                lease_seconds=config.lease_seconds,
                timeout_seconds=config.timeout_seconds,
                retry_after_seconds=config.retry_after_seconds,
            )

            if outcome is None:
                if config.idle_sleep_seconds:
                    sleep(config.idle_sleep_seconds)
                continue

            attempted += 1
            if isinstance(outcome, CollectedJob):
                succeeded += 1
            elif isinstance(outcome, FailedJob):
                failed += 1
            else:  # pragma: no cover - defensive contract guard
                raise RuntimeError("unexpected detailed collector result")

        return SingleNodeRuntimeResult(
            jobs_attempted=attempted,
            jobs_succeeded=succeeded,
            jobs_failed=failed,
            feeder_passes=feeder_passes,
            jobs_materialized=materialized,
            stopped_by_control=stopped_by_control,
        )
    finally:
        with engine.begin() as conn:
            stop_collector(conn, collector_uuid=identity.collector_uuid)
