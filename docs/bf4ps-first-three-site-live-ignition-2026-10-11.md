# BF4PS — first three-site REAL Battlelog ignition (2026-10-11)

**PASS: 9/9 detailed-statistics collections, three distinct physical test nodes. Production HOLD unchanged.**

## Test boundary

- Nodes: `tcou`, `kah-01`, `hnl-01`; **not** `mak-01`.
- PostgreSQL: `mak-db-02.bf4statusbot.com`, isolated `bf4ps_scratch_stage9c_d2`, role `bf4ps_stage9c_d2`, writable primary, Alembic `0005_stage9c_dispatch_ledger`.
- Test harness: `scripts/stage9c_three_site_live_ignition.py` on branch `fix/stage9c-t4-inspector-lease-expiry`.
- Run: `bf4ps-live-three-site-ignition-20261011-v1`.
- Exactly 9 known PC persona IDs, 3 per node; detailed resource only. 3 uniquely registered collector UUIDs and egress keys. Shared DB job queue, shared 9-attempt ceiling, production background admission, 10-second per-egress request gate. Explicit `--execute` required.
- Test DB was empty before preparation. Preparation inserted 9 soldiers, 9 jobs, 3 collectors.

## Observed results

| Node | Soldier | Rank | Kills |
|---|---|---:|---:|
| tcou | It_Mip | 95 | 12341 |
| tcou | malilahygge | 84 | 7534 |
| tcou | JonNZzin | 140 | 115019 |
| kah-01 | GORBON_TREEMAN | 99 | 11331 |
| kah-01 | stelyo_berberaks | 140 | 90119 |
| kah-01 | pirulaconcaca | 44 | 4105 |
| hnl-01 | yukonsunshine | 140 | 73870 |
| hnl-01 | FrankoPop | 130 | 38381 |
| hnl-01 | MLGPILLO | 49 | 5052 |

- `tcou` exit 0, 21.18 seconds, 3/3 successful.
- `kah-01` exit 0, 23.12 seconds, 3/3 successful.
- `hnl-01` exit 0, 23.28 seconds, 3/3 successful.
- Post-run `verify` on `tcou` exit 0: `VERIFY soldiers=9 events=18 pending_jobs=0`; all nine detailed states `success`, rank populated, history=1, exactly `collection_attempt_started` and `collection_success`, each attributed to its assigned collector UUID. Final `THREE-SITE LIVE IGNITION PASS`.

## Harness race discovered and corrected

The initial simultaneous launch revealed a preflight assumption that all nine jobs would still be queued. `tcou` completed its first job before `kah-01` and `hnl-01` performed their queue checks. Both remote harnesses correctly stopped without HTTP. The harness was patched to allow jobs already completed by another partition, while strictly requiring its own three jobs to remain pending and free of prior events. Re-launch of the two remote harnesses succeeded. Fix commit `b87a916`.

This is a **harness preflight race**, not a duplicate collector claim or PostgreSQL persistence failure.

## What this proves — and what remains

Proven: three distinct physical test nodes performed actual Battlelog detailed requests, concurrently, through the same writable test database; persisted current and historical statistics and durable events with correct node attribution, without duplicate collection or residual jobs.

Not yet proven: live multi-resource three-site workloads, mixed PC/PS4/Xbox three-site distribution, dynamic queue balancing/stealing rather than fixed three-soldier partitions, lease-expiry crash recovery, multi-hour live soak, or sustained-rate/HTTP error behavior. Do not call the system production-ready yet. Do not touch production BF4SW.
