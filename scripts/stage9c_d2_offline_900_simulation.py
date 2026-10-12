"""Deterministic, in-memory 900-soldier scheduler stress harness.

No database, network, collector runtime, or Battlelog imports. This models
site-owned FIFO queues and interleaved claims; it is not a throughput benchmark.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, deque

SITES = ("tcou", "kah-01", "hnl-01")


def simulate(*, soldiers=900, rounds=12, seed=20261011):
    if soldiers <= 0 or soldiers % len(SITES) or rounds <= 0:
        raise ValueError("soldiers must be a positive multiple of three; rounds positive")
    per_site = soldiers // len(SITES)
    owners = {sid: SITES[(sid - 1) // per_site] for sid in range(1, soldiers + 1)}
    rng = random.Random(seed)
    totals = Counter()
    round_results = []
    ownership_violations = []
    for number in range(1, rounds + 1):
        queues = {site: deque(sid for sid in range(1, soldiers + 1)
                              if owners[sid] == site) for site in SITES}
        seen = set()
        round_counts = Counter()
        while any(queues.values()):
            # Randomize scheduling opportunity, but never transfer job ownership.
            site = rng.choice([s for s in SITES if queues[s]])
            sid = queues[site].popleft()
            if sid in seen or owners[sid] != site:
                ownership_violations.append((number, site, sid))
            seen.add(sid)
            totals[site] += 1
            round_counts[site] += 1
        if len(seen) != soldiers:
            raise AssertionError("lost jobs")
        round_results.append({"round": number, "completed": len(seen),
                              "by_site": dict(round_counts)})
    return {
        "mode": "offline_simulation", "soldiers": soldiers, "rounds": rounds,
        "seed": seed, "per_site": per_site, "total_claims": sum(totals.values()),
        "by_site": dict(totals), "ownership_violations": ownership_violations,
        "rounds_detail": round_results,
        "limitations": "In-memory ownership/FIFO scheduling model only; does not execute SQL claims, leases, network calls, or real collector throughput.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--soldiers", type=int, default=900)
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20261011)
    args = parser.parse_args()
    print(json.dumps(simulate(soldiers=args.soldiers, rounds=args.rounds, seed=args.seed),
                     sort_keys=True))


if __name__ == "__main__":
    main()
