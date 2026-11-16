# General ranking full-scope scratch publisher benchmark — 2026-11-16

**Status:** executed successfully on isolated RNT-01 PostgreSQL 16 scratch. NOT production; no replica lag measured.

## Preconditions and isolation

- Repository docs/database-schema-reference.md and migration 0026_general_rank_snapshots.py were inspected before SQL work.
- RNT-01 local scratch PostgreSQL cluster bf4psscratch, port 5542, database bf4ps_rank_scratch, Alembic 0026_general_rank_snapshots.
- Synthetic 560,000-soldier source cohort; benchmark published metric wins / platform all.
- The existing production database and website feature flag were not touched.
- Executed publisher build_scope in a single transaction, followed by committed pointer and row-count verification.

## Observed measurements

| Measurement | Observed |
|---|---:|
| Generation | 8 |
| Committed rows / population | 560,000 |
| Publisher elapsed time | 6.690 seconds |
| WAL LSN before | 0/5C4DA9B8 |
| WAL LSN after | 0/68898750 |
| WAL delta | 205,249,944 bytes (195.74 MiB) |
| general_rank_rows relation size before | 329,818,112 bytes |
| Relation growth | 115,064,832 bytes (109.73 MiB) |
| Published pointer and row-count check | PASS |

The relation-size delta includes index/relation allocation effects. The WAL delta measures the isolated scratch cluster over the benchmark interval, not an exact attribution of every byte to a specific statement. The reported elapsed time covers the transaction including commit.

## Interpretation and deployment constraints

- One 560k-player full-scope build completed in under seven seconds in this environment; this is **not** a guarantee for all 56 scopes or for production hardware and concurrency.
- A naïve linear multiplication of this one run by 56 would be approximately 10.7 GiB WAL and 6.0 GiB of additional row relation storage for one generation per scope, but **this is an illustrative projection, not a measured 56-scope result**. Platform-specific cohorts, metrics, index growth, retention, and compression differ.
- No streaming replicas exist in this isolated scratch cluster; replica lag and production WAL replay effects remain unmeasured.
- The writer's global advisory lock serializes scopes. A scheduler and bounded retention service remain absent.
- Repeat builds and cleanup must be measured before continuous production publication to prevent uncontrolled growth.
- Production Alembic 0026 rollout, permissions, current disk/WAL/replica health, complete parity checks, and a one-node production canary remain mandatory.

## Reproducibility

The executed scratch-only benchmark harness is currently at
`/tmp/bf4ps_publish_benchmark.py` on RNT-01. The SQLAlchemy WAL difference
uses `pg_wal_lsn_diff(CAST(:a AS pg_lsn),CAST(:b AS pg_lsn))`.
It must never be run against a production connection string without a separate
approved production canary plan. It inserts and publishes a new generation.
