# Stage 9C D2 — full-capacity SQL ledger boundary checkpoint (2026-10-10)

**Operator-reported PASS** on tcou, isolated D2 scratch database at `0005_stage9c_dispatch_ledger`. Production remains HOLD.

```text
.venv/bin/python -m scripts.phase5b_stage9c_d2_sql_full_boundary --execute
PASS: 1295 actual synthetic ledger rows + 2 concurrent contenders; one admitted, one denied
PASS: post-race real SQL usage=1296; run-scoped ledger rows=1296
LIMIT: D2 scratch only, no physical HTTP dispatch or production admission
```

The harness `scripts/phase5b_stage9c_d2_sql_full_boundary.py` (commit `3444381`) inserted 1295 real synthetic `outbound_dispatches` records in the dedicated scratch database. Two independent transactions competed under the existing background advisory transaction lock, sampled PostgreSQL `clock_timestamp()` after acquiring it, and used the actual three-source SQL accounting query. One admitted, one denied. Subsequent SQL accounting and scoped row count both returned 1296. Harness cleanup is scoped by its random run egress key, job range and fixture fingerprints.

This proves a controlled database-backed 1295-to-1296 admission boundary with two contenders. It does **not** prove global physical-send rate compliance, bounded admission-to-send latency, replay/failover safety, collector ownership, per-egress pacing, class fairness, or full adversarial concurrency behavior.

Next design work should address the **physical-send guarantee** before any collector integration or production activation. Admission timestamps alone do not bound arbitrarily delayed network sends; a reserved dispatch can be physically sent long after its recorded admission, causing more than 1296 sends in a later rolling hour. Do not represent ledger admission as physical-send accounting.

T4 scratch at `0004` remains separate; no HTTP or production migrations are authorized.
