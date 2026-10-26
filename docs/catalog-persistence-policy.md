# Shared equipment catalog write policy

The authoritative weapon/vehicle catalogs use stable GUIDs and catalog IDs.
Every successful soldier fetch persists all of that soldier's current statistics
atomically with job completion, independent of catalog metadata refresh.

New GUIDs are inserted immediately. Existing catalog metadata (name, slug, category)
is reconciled at most once per 15 minutes per catalog item, even if changed across platforms. To prevent shared-row contention and
unbounded MVCC dead tuples, unchanged catalog entries are not updated for every
soldier. Their `last_seen_at` is refreshed no more often than once per 15 minutes
when encountered; it is therefore an approximate last-observed timestamp,
not an exact per-fetch audit trail. The collection events and soldier stat
`source_fetched_at` remain the authoritative per-fetch timestamps.

The transaction-scoped catalog advisory locks remain in place for actual
catalog reconciliation, but ordinary soldier-stat writes no longer acquire
them. If a catalog change is needed, the worker acquires the lock and rechecks
existing rows before writing, preventing concurrent catalog races. GUID
ordering, queue leases, request pacing and production dispatch budgets remain
unchanged. Only stale, changed, or missing catalog entries are written. This is intentionally not a schema migration.

Production evidence before this optimization: 174 weapon catalog entries with
~1.60M dead tuples, and 82 vehicle entries with ~755K dead tuples. Regular
VACUUM can recover dead tuple space for reuse; separately evaluate index bloat
and any `REINDEX CONCURRENTLY` operation under maintenance procedures.

## Production import-path warning (2026-10-25)

The collector starts from `/app/scripts` and imports the installed `bf4ps` package under `/usr/local/lib/python3.12/site-packages/bf4ps/`. An image that only replaces `/app/bf4ps/` **does not** activate the optimized catalog persistence. Use `player-collector/deploy/docker/Dockerfile.catalog-installed-hotfix` or a clean package rebuild and verify the actual imported file from the entrypoint working directory. See [CATALOG-IMPORT-PATH-RECOVERY-20261025.md](CATALOG-IMPORT-PATH-RECOVERY-20261025.md).
