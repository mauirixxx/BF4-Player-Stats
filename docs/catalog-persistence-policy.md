# Shared equipment catalog write policy

The authoritative weapon/vehicle catalogs use stable GUIDs and catalog IDs.
Every successful soldier fetch persists all of that soldier's current statistics
atomically with job completion, independent of catalog metadata refresh.

Catalog metadata (name, slug, category) is reconciled immediately if changed,
and new GUIDs are inserted immediately. To prevent shared-row contention and
unbounded MVCC dead tuples, unchanged catalog entries are not updated for every
soldier. Their `last_seen_at` is refreshed no more often than once per 15 minutes
when encountered; it is therefore an approximate last-observed timestamp,
not an exact per-fetch audit trail. The collection events and soldier stat
`source_fetched_at` remain the authoritative per-fetch timestamps.

The transaction-scoped catalog advisory locks, GUID ordering, queue leases,
request pacing and production dispatch budgets remain unchanged. Existing
catalog IDs are loaded before the optional bulk upsert; only stale, changed,
or missing entries are written. This is intentionally not a schema migration.

Production evidence before this optimization: 174 weapon catalog entries with
~1.60M dead tuples, and 82 vehicle entries with ~755K dead tuples. Regular
VACUUM can recover dead tuple space for reuse; separately evaluate index bloat
and any `REINDEX CONCURRENTLY` operation under maintenance procedures.