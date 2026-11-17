# General ranking cycle runner — isolated validation, 2026-11-17

**Status:** Explicit one-scope runner tested on RNT-01 scratch. No timer, daemon, fleet service, or production activation.

Source: `player-collector/bf4ps/general_rank_cycle.py`.

The runner requires Alembic 0026, chooses a never-published metric/platform scope first, otherwise the oldest `published_at` scope, and uses a deterministic metric/platform tie-breaker. `--execute` is mandatory for writes; no flag means a read-only selection preview. Execution acquires the shared general ranking advisory transaction lock BEFORE choosing the next scope, then calls `build_scope()` and commits its generation and pointer in one transaction. Thus concurrent runners serialize and cannot choose the same stale scope. There are 14 metrics and 4 platforms (56 scopes).

**Scratch evidence:** RNT-01 PostgreSQL `bf4ps_rank_scratch` port 5542, Alembic 0026. Dry-run chose `kills/all` without publishing. Explicit `--execute` published `kills/all`, generation 153, population 560,000, process exit code 0, runtime 10.96 seconds. Five new offline runner tests passed; selected combined regression suite 21/21.

**Limitations:** This is NOT an automatic continuous scheduler, and there is no timer or service definition. It does not perform cleanup; invoke the separate bounded retention worker only under a measured, approved cadence. The shared global advisory lock serializes all general ranking publications and cleanup. No throughput target, WAL budget, replica impact, storage capacity, monitoring, or production migration approval is implied. A new invocation chooses the next scope; callers must explicitly control frequency and resource budgets. It is not safe to enable unattended execution until production database capacity/replication issues are resolved in the separate incident workflow.

**Development rule:** Before any schema-dependent changes, re-read `docs/database-schema-reference.md` and current Alembic migrations. Production 0026 was not deployed in this work.
