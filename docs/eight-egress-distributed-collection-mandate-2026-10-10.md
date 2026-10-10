# BF4 Player Stats — eight-egress distributed collection mandate (2026-10-10)

**AUTHORITATIVE ARCHITECTURE SCOPE UPDATE.** This supersedes any suggestion that a single active HTTP gateway is the preferred production target. The operator confirms **all eight planned nodes have their own dedicated public egress IP by design**. The project is intended to collect statistics for approximately 200,000 players with eight independently fetching workers, not eight workers queued behind one external egress IP.

## Non-negotiable target

1. Up to eight active collectors, each using its own dedicated public egress IP to fetch assigned Battlelog statistics. Keep distributed PostgreSQL job coordination, per-egress pacing and HA/recovery. Do not consolidate physical HTTP traffic through a single egress IP.
2. Best-effort deduplication is sufficient for *work scheduling*. Concurrent duplicate fetches may happen; this is accepted operational waste, not an automatic incident.
3. **First valid committed result wins** for an equivalent collection job/snapshot. Discard later redundant results instead of overwriting the winner; preserve atomic ownership/commit semantics. Do not silently treat an older fetched snapshot as newer.
4. Log every **observed discarded duplicate result** with event type `collection_duplicate_discarded` in existing `collection_events`. Record collector, soldier, resource, platform, job/attempt identity where available, and a bounded reason in metadata. Log duplicates only when observed; do not invent counts from prevented jobs. Exclude secrets and large payloads.
5. Failed fetches return to the **back of the eligible queue**, with bounded retry/backoff and no immediate retry storms. Existing `collection_failure` event rows and `eligible_at` retry scheduling should be reused; preserve error class and HTTP status. A global throttle response (403/429) may require stronger coordinated cooldown rather than merely individual requeue.
6. Measure duplicate discard counts and failure/retry counts by node, egress, resource and time period; revisit dedup sophistication if waste becomes significant.
7. The separate operator-defined hard constraint remains **at most 1296 ACTUAL physical HTTP dispatches in ANY rolling 3600 seconds globally**, plus per-egress pacing. Eight dedicated IPs do **not** remove that global constraint. Do not confuse logical request admission with physical dispatch. Production remains HOLD until this safety requirement is resolved or explicitly revisited with the operator.

## Existing schema assessment (documentation + migration 0001)

- `collection_jobs`: UNIQUE `(soldier_id, resource)`, statuses `pending/claimed/running`, `eligible_at`, lease and retry fields. Existing collectors already reschedule failures by setting `pending` and future `eligible_at`.
- `collection_events`: flexible nonempty `event_type`, `result`, `error_class`, `http_status`, `metadata` JSONB, job, soldier, platform, resource, collector, hostname, egress. No event-type enum constraint. Existing indexes cover event type/time, collector/time and soldier/time.
- Therefore **no database migration is required just to add a duplicate-discard event**. Do not modify migration 0001 or deploy a schema change without a proven need.
- `detailed_stats_current` currently has an unconditional `ON CONFLICT (soldier_id) DO UPDATE` in `bf4ps/detailed_persistence.py`. Existing job lease ownership limits overlap, but it does not itself establish first-result-wins across all potential stale or out-of-order collection scenarios. Weapon and vehicle paths must be independently checked before changing their persistence behavior.

## Implementation acceptance criteria

- Duplicate completion loses safely in a DB transaction; no overwrite, no false success, and a durable `collection_duplicate_discarded` event, including when the original job has already been deleted (nullable job reference).
- Dedup log writes must not violate FK constraints; stale worker may lack a valid lease/collector identity. Preserve forensic snapshots where available.
- Retry scheduling uses existing priority and `eligible_at` semantics. Verify actual queue ordering and that back-of-line behavior is fair at scale.
- Duplicate metrics are cheap read-only aggregates on `collection_events`; distinguish *prevented duplicate jobs* from *discarded duplicate HTTP results*.
- Tests include concurrent winners/losers, stale leases, multiple resource types, failure requeue, and repeat duplicates.
- No production DB writes or HTTP until separately approved.

## Next work

Implement schema-aligned read-only duplicate/failure reporting and inspect persistence functions for precise stale-result handling. Then implement a scratch-tested transactional duplicate-discard event path. Preserve the original distributed eight-egress target.
