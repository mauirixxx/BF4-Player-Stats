"""Offline three-site coordinator: deterministic plans and result validation.

No remote execution, PostgreSQL writes, HTTP or secrets. A future executor
can consume these plans only after independent D2 authorization gates.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass

from scripts.phase5b_three_site_worker import ALLOWED_HOSTS, MAX_WORKERS_PER_HOST, WorkerConfig

DEFAULT_DISTRIBUTION = {"tcou": 3, "kah-01": 3, "hnl-01": 2}


@dataclass(frozen=True)
class FleetPlan:
    run_id: str
    distribution: dict[str, int]

    @classmethod
    def build(cls, run_id: str, distribution: dict[str, int]):
        if not distribution or set(distribution) - ALLOWED_HOSTS:
            raise ValueError("only approved three-site hosts are allowed")
        if any(not isinstance(n, int) or isinstance(n, bool) or
               not 0 <= n <= MAX_WORKERS_PER_HOST for n in distribution.values()):
            raise ValueError("each host must have 0..32 workers")
        if not 1 <= sum(distribution.values()) <= 96:
            raise ValueError("fleet must contain 1..96 workers")
        first_host, first_count = next((h, n) for h, n in distribution.items() if n)
        WorkerConfig.build(host=first_host, worker_index=0,
                           workers_on_host=first_count, run_id=run_id)
        return cls(run_id, dict(distribution))

    def workers(self):
        return [
            WorkerConfig.build(host=host, worker_index=index,
                               workers_on_host=count, run_id=self.run_id)
            for host, count in sorted(self.distribution.items())
            for index in range(count)
        ]

    def report(self):
        workers = self.workers()
        return {
            "run_id": self.run_id,
            "distribution": self.distribution,
            "worker_count": len(workers),
            "unique_collector_count": len({str(w.collector_uuid) for w in workers}),
            "workers": [w.report() for w in workers],
            "mode": "dry-run",
            "database_writes": 0,
            "http_requests": 0,
        }


def validate_claim_results(expected_job_ids: set[int], claims: list[dict]) -> dict:
    """Reject duplicate (job, attempt) owners; report distribution, no DB IO."""
    seen = set()
    by_host = Counter()
    for claim in claims:
        host = claim["host"]
        job = claim["job_id"]
        attempt = claim["attempt_count"]
        if host not in ALLOWED_HOSTS or job not in expected_job_ids or attempt < 1:
            raise ValueError("unrecognized claim host, job, or attempt")
        key = (job, attempt)
        if key in seen:
            raise ValueError(f"duplicate committed claim: {key}")
        seen.add(key)
        by_host[host] += 1
    return {
        "claims": len(claims),
        "distinct_attempts": len(seen),
        "duplicates": 0,
        "per_host": dict(sorted(by_host.items())),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tcou", type=int, default=3)
    parser.add_argument("--kah-01", type=int, default=3)
    parser.add_argument("--hnl-01", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        plan = FleetPlan.build(args.run_id, {
            "tcou": args.tcou, "kah-01": args.kah_01, "hnl-01": args.hnl_01
        })
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(plan.report(), sort_keys=True))


if __name__ == "__main__":
    main()
