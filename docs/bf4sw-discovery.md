# BF4SW discovery and reconciliation

BF4 Player Stats can use an existing BF4 Server Watcher PostgreSQL database as a discovery source. Deployment-specific hostnames, addresses, credentials, DNS layout, and infrastructure topology are intentionally outside the scope of this document.

## Connection configuration

The BF4PS destination database is configured with `BF4PS_DATABASE_URL`. The read-only BF4 Server Watcher source is configured separately with `BF4PS_BF4SW_DATABASE_URL`. Keeping the two URLs separate prevents the source and destination roles from being conflated.

## New-alias discovery

`python -m bf4ps.discovery --discover` reads a bounded batch of BF4SW alias rows whose numeric alias ID is greater than the persistent `bf4sw` discovery cursor. `--discover-until-caught-up` repeats bounded batches until no newer alias rows remain.

For every identity encountered, BF4PS imports the BF4SW alias history idempotently. Existing `(persona_id, platform)` soldiers are updated rather than duplicated, name history is upserted, the BF4SW source observation is updated, and collection state is created only when absent.

The alias-ID cursor is intentionally responsible only for discovering new rows. BF4SW can continue changing `last_seen` on an old alias row without allocating a new alias ID, so the discovery cursor alone cannot keep mutable observations synchronized.

## Mutable-observation reconciliation

`python -m bf4ps.discovery --reconcile` refreshes BF4SW aliases selected by recent `last_seen` activity.

The first reconciliation uses a 24-hour activity window by default. Later runs use the previous successful source watermark with a 15-minute overlap. Both values are configurable with `--reconcile-window-hours` and `--reconcile-overlap-minutes` while the feature is being validated.

The reconciliation watermark is stored as a second `discovery_state` row named `bf4sw_reconcile`; no schema migration is required. The watermark comes from `clock_timestamp()` on the BF4SW source database, rather than the application host's wall clock. This makes reconciliation independent of whether hosts display local time or UTC and reduces sensitivity to small host-clock differences. PostgreSQL timezone-aware timestamps remain the canonical observations.

The overlap is deliberate. Reprocessing is idempotent, while overlapping the previous watermark protects boundary updates from being missed.

Discovery and reconciliation are separate explicit operations at this stage. Reconciliation should be validated against a disposable/test BF4PS database before it is placed into an automatic service loop.

## Validation record

Live-source validation on 2026-10-02/03 established the following behavior at the tested checkpoints:

- historical bootstrap reconciled exactly 176,802 BF4SW `(persona_id, platform)` identities into BF4PS, with zero missing identities, zero extra identities, and zero duplicate identity groups;
- 179,319 immutable BF4SW name-history keys reconciled exactly into BF4PS;
- soldier aggregation checks across all 176,802 soldiers found zero first/last timestamp problems and zero current-name problems;
- a subsequent 100-row discovery batch advanced the persistent cursor from 179547 to 179647, produced 98 new soldiers and two new aliases for existing soldiers, and had zero missing destination soldiers or name rows;
- mutable-observation analysis found 4,779 imported alias rows whose BF4SW `last_seen` had advanced after import;
- aliases still receiving updates were as old as approximately 44 days, demonstrating that alias age or a numeric-ID overlap is not a safe reconciliation criterion; and
- all 4,779 stale observations in that measurement had BF4SW activity within the preceding six hours, supporting recent `last_seen` activity as the reconciliation selector while retaining a more conservative 24-hour initial window.

These measurements describe the validation dataset at that point in time; they are evidence for the design, not permanent assumptions about BF4SW activity distribution.
