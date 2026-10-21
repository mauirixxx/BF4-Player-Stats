# Runtime budgets and nonfatal exhaustion (migration 0008)

## Source of truth

Production PostgreSQL database `bf4_playerstats` is the sole authority for the two fleet-wide hourly limits. Migration `0008_runtime_budgets` creates singleton table `runtime_budgets` with `singleton = true`, `physical_dispatches_per_hour`, `background_slots_per_hour`, and `updated_at`. Initial values are 4800 and 4800. The database validates positive limits, maximum 5760 physical dispatches per rolling hour, and background slots no greater than physical capacity. No new collectors are automatically enabled by migration.

## Runtime semantics

Every physical HTTP admission holds the existing PostgreSQL transaction advisory lock, counts the last rolling 3600 seconds, then reads the physical limit from the same database transaction. No process-local cache is authoritative. The background admission path reads its hourly slots under the existing scheduler advisory lock and computes 75% active, 20% bootstrap, and remaining recovery floors on each decision. Interactive dispatches count against the physical limit.

When a physical dispatch is refused because the budget is full, the collector remains running, sleeps 15 seconds, continues to heartbeat, and retries through the normal admission path. HTTP 403/429 throttles still stop the collector as before. Job lease ownership and durable dispatch accounting remain unchanged.

## Rollout and rollback

Run tests and verify live schema revision 0007 before migration. Apply additive migration 0008 while old collectors are running; they do not use the new table. Build and restart one collector, validate heartbeat and successful requests, then roll the remaining seven. Migration 0008 is required before the updated collector can start. Do not downgrade schema while updated collectors run. Preserve backups and do not alter BF4 Server Watcher services.

## Operator tuning

Change the two values together in one transaction; use `UPDATE runtime_budgets SET physical_dispatches_per_hour = ..., background_slots_per_hour = ..., updated_at = now() WHERE singleton = true`. Database constraints reject invalid combinations. The current upper bound of 5760 is a safety policy, not a promise Battlelog tolerates that throughput. Monitor throttling, dispatch count, and collector heartbeats after each increase.
