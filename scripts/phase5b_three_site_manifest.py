"""Offline distributed run manifest for a future D2-only execution.

This module never opens a database, starts workers, or makes HTTP requests.
A coordinator can generate and verify the same immutable manifest on each
host before enabling any separately authorized scratch-database exercise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass

from scripts.phase5b_three_site_coordinator import FleetPlan


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    distribution: dict[str, int]
    job_count: int
    claim_limit_per_worker: int
    lease_seconds: int

    @classmethod
    def build(cls, *, run_id: str, distribution: dict[str, int],
              job_count: int = 64, claim_limit_per_worker: int = 16,
              lease_seconds: int = 120):
        plan = FleetPlan.build(run_id, distribution)
        if not 1 <= job_count <= 10000:
            raise ValueError("job-count must be 1..10000")
        if not 1 <= claim_limit_per_worker <= 10000:
            raise ValueError("claim-limit must be 1..10000")
        if not 30 <= lease_seconds <= 3600:
            raise ValueError("lease-seconds must be 30..3600")
        return cls(plan.run_id, plan.distribution, job_count,
                   claim_limit_per_worker, lease_seconds)

    def payload(self):
        plan = FleetPlan.build(self.run_id, self.distribution)
        return {
            "schema": "bf4ps-d2-three-site-manifest-v1",
            "run_id": self.run_id,
            "distribution": dict(sorted(self.distribution.items())),
            "job_count": self.job_count,
            "claim_limit_per_worker": self.claim_limit_per_worker,
            "lease_seconds": self.lease_seconds,
            "worker_count": len(plan.workers()),
            "collector_uuids": sorted(str(w.collector_uuid) for w in plan.workers()),
            "synthetic_only": True,
            "http_enabled": False,
            "production_enabled": False,
        }

    def report(self):
        payload = self.payload()
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return {"manifest": payload,
                "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def validate_manifest_document(document: dict) -> RunManifest:
    if not isinstance(document, dict) or set(document) != {"manifest", "sha256"}:
        raise ValueError("invalid manifest envelope")
    payload = document["manifest"]
    if not isinstance(payload, dict):
        raise ValueError("invalid manifest payload")
    expected_fields = {
        "schema", "run_id", "distribution", "job_count",
        "claim_limit_per_worker", "lease_seconds", "worker_count",
        "collector_uuids", "synthetic_only", "http_enabled",
        "production_enabled",
    }
    if set(payload) != expected_fields:
        raise ValueError("invalid manifest fields")
    if (payload["schema"] != "bf4ps-d2-three-site-manifest-v1"
            or payload["synthetic_only"] is not True
            or payload["http_enabled"] is not False
            or payload["production_enabled"] is not False):
        raise ValueError("unsafe or unsupported manifest")
    manifest = RunManifest.build(
        run_id=payload["run_id"], distribution=payload["distribution"],
        job_count=payload["job_count"],
        claim_limit_per_worker=payload["claim_limit_per_worker"],
        lease_seconds=payload["lease_seconds"],
    )
    if manifest.report() != document:
        raise ValueError("manifest content or digest mismatch")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tcou", type=int, default=3)
    parser.add_argument("--kah-01", type=int, default=3)
    parser.add_argument("--hnl-01", type=int, default=2)
    parser.add_argument("--job-count", type=int, default=64)
    parser.add_argument("--claim-limit-per-worker", type=int, default=16)
    parser.add_argument("--lease-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    try:
        manifest = RunManifest.build(
            run_id=args.run_id,
            distribution={"tcou": args.tcou, "kah-01": args.kah_01, "hnl-01": args.hnl_01},
            job_count=args.job_count,
            claim_limit_per_worker=args.claim_limit_per_worker,
            lease_seconds=args.lease_seconds,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(manifest.report(), sort_keys=True))


if __name__ == "__main__":
    main()
