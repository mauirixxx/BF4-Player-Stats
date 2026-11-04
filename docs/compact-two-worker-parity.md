# Compact ranking: two parity workers

Production layout (2026-11-04):
- MAK-01: `BF4PS_COMPACT_SCOPE_PARITY=odd`
- MAK-02: `BF4PS_COMPACT_SCOPE_PARITY=even`
- Both use the same `player-collector/run_compact_rank_scheduler.py` and
  `bf4ps-compact-ranking.service` implementation.
- Parity applies to `equipment_rank_jobs.item_id` for **both weapons and vehicles**,
  across PC, PS4, Xbox One and ALL, and all supported metrics.
- `all` is the default, for a one-worker deployment or bounded testing.
- The production singleton `equipment_rank_capacity.max_active_builds` is set to
  **2** (an application-level capacity limit, not a PostgreSQL limit).
- The existing lease/fencing, publication guards, and
  `public.bf4ps_rank_gate_ready()` checks remain in place.
- MAK-01 and MAK-02 use host-specific systemd units with Docker
  `-e BF4PS_COMPACT_SCOPE_PARITY=odd` and `even` respectively.
- The independent hourly retention timer stays on MAK-01 only.

## Safe rollout and validation

1. Confirm schema reference and Alembic migrations before DB operations.
2. Stage identical scheduler and compact build code on both hosts.
3. Run a bounded `--max-publications 2 --parity even` smoke test on MAK-02.
4. Increase `equipment_rank_capacity.max_active_builds` from 1 to 2.
5. Restart MAK-01 with `odd`, start MAK-02 with `even`.
6. Verify each host publishes only its parity and the WAL replay gate
   remains ready with low byte-level lag on all replicas.
7. A stopped worker may leave an unexpired claim lease (default 180s).
   Do not interpret this as a live worker; allow lease expiry or perform
   a separately verified fenced recovery before investigating claim failures.
8. If replication pressure increases, stop MAK-02 first, wait for active
   claims to drain, set capacity back to 1, and set MAK-01 parity to `all`.

## Monitoring

The admin ranking monitor shows the configured capacity, active database
claims, and recent publications. A claim is not a verified process heartbeat.
Keep checking host systemd status and publication logs separately.

A two-worker ideal speedup is not guaranteed: scope sizes and WAL-gate waits
can vary, and the even/odd partitions may have different scope counts.
