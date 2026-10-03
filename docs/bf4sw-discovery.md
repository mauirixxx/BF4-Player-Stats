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

## Unattended service loop

`python -m bf4ps.discovery_service` combines the two validated operations into a foreground service suitable for supervision by systemd.

On startup the service first runs discovery until caught up, then immediately runs reconciliation. In steady state it catches discovery up every 60 seconds and reconciles every five minutes by default. These intervals can be changed with `--discovery-interval-seconds` and `--reconcile-interval-seconds` during validation.

Discovery and reconciliation remain independent failure domains. An exception in one cycle is logged and that operation is retried on its next scheduled cycle; it does not intentionally advance the failed operation's durable checkpoint and does not prevent the other operation from running. The first consecutive failure for each operation includes its traceback. Repeated failures are logged as concise error messages until that operation succeeds again, at which point the service logs a recovery message and resets the failure counter.

The service obtains a session-level PostgreSQL advisory lock on the BF4PS destination before doing any work. A second service process targeting the same destination database exits instead of creating two concurrent discovery/reconciliation loops. The lock is held by a dedicated destination connection for the lifetime of the process and PostgreSQL also releases it automatically if that connection disappears.

SIGINT and SIGTERM request an orderly shutdown. The runner remains a foreground process; daemonization and restart policy belong to the process supervisor rather than the application.

## systemd test-soak deployment

The repository includes `deploy/systemd/bf4ps-discovery.service`. It is intended first for an unattended soak against a disposable BF4PS test database, not as authorization to switch the destination to production.

The unit expects the checkout at `/var/www/bf4playerstats.com`, its virtual environment at `/var/www/bf4playerstats.com/.venv`, a dedicated `bf4ps` service account, and an environment file at `/etc/bf4-player-stats/discovery.env`. The environment file must define both `BF4PS_DATABASE_URL` and `BF4PS_BF4SW_DATABASE_URL`; credentials must not be committed to the repository. During the soak, `BF4PS_DATABASE_URL` must continue to target the disposable/test BF4PS database.

A typical installation after creating the service account and protected environment file is:

```sh
install -m 0644 deploy/systemd/bf4ps-discovery.service /etc/systemd/system/bf4ps-discovery.service
systemctl daemon-reload
systemctl enable --now bf4ps-discovery.service
systemctl status bf4ps-discovery.service
journalctl -u bf4ps-discovery.service -f
```

The unit runs the application in the foreground, starts after network-online, restarts on failure after five seconds, and allows up to 30 seconds for orderly shutdown. The PostgreSQL advisory lock remains the authoritative protection against accidentally running a second discovery loop against the same BF4PS destination.

For upgrades, pull the validated repository branch, run the test suite, then restart the service and inspect its journal. A repository update alone does not change the running process until it is restarted.

Before any production destination is configured, soak validation should include sustained normal operation, reboot/startup behavior, journal review, continued movement of both discovery-state checkpoints, source-to-destination reconciliation audits, and confirmation that source outages recover without operator state repair.

## Validation record

Live-source validation on 2026-10-02/03 established the following behavior at the tested checkpoints:

- historical bootstrap reconciled exactly 176,802 BF4SW `(persona_id, platform)` identities into BF4PS, with zero missing identities, zero extra identities, and zero duplicate identity groups;
- 179,319 immutable BF4SW name-history keys reconciled exactly into BF4PS;
- soldier aggregation checks across all 176,802 soldiers found zero first/last timestamp problems and zero current-name problems;
- a subsequent 100-row discovery batch advanced the persistent cursor from 179547 to 179647, produced 98 new soldiers and two new aliases for existing soldiers, and had zero missing destination soldiers or name rows;
- mutable-observation analysis found 4,779 imported alias rows whose BF4SW `last_seen` had advanced after import;
- aliases still receiving updates were as old as approximately 44 days, demonstrating that alias age or a numeric-ID overlap is not a safe reconciliation criterion; and
- all 4,779 stale observations in that measurement had BF4SW activity within the preceding six hours, supporting recent `last_seen` activity as the reconciliation selector while retaining a more conservative 24-hour initial window.

The reconciliation implementation was then exercised directly against the disposable BF4PS test database while BF4SW remained live:

- the initial 24-hour reconciliation selected 26,800 alias rows representing 26,768 identities and completed in approximately 44.2 seconds;
- the first steady-state incremental run used the prior source watermark plus the configured 15-minute overlap, selected 1,792 aliases/identities, and completed in approximately 3.9 seconds;
- the next incremental run again used the overlapping watermark window, selected 1,666 aliases/identities, and completed in approximately 3.3 seconds;
- the normal `bf4sw` discovery cursor remained unchanged at 179647 throughout reconciliation, confirming that discovery and reconciliation maintain independent progress state;
- no audited BF4PS observation was newer than its corresponding BF4SW source observation; and
- rows reported as BF4SW-newer immediately after a reconciliation were verified to include source mutations occurring after that run's source-database cutoff. Those rows are expected to be consumed by a later overlapping reconciliation run rather than indicating a missed boundary update.

The unattended runner was then validated manually against the disposable destination. It caught up new aliases, continued incremental discovery, reconciled on schedule, rejected a concurrent second instance through the advisory lock, resumed durable checkpoints after clean restart, survived repeated source-connection failures without terminating, and automatically caught up and resumed reconciliation after the source connection was restored. SIGINT produced orderly shutdowns throughout validation.

The synchronization target is therefore bounded eventual consistency, not a permanently zero-difference comparison against a source database that continues to mutate during and after each reconciliation transaction.

The application host and PostgreSQL host may display different local time zones without affecting reconciliation correctness. Validation used an application host displaying HST and a PostgreSQL host displaying UTC; reconciliation boundaries are derived from the BF4SW PostgreSQL source clock and timezone-aware timestamps rather than the application's displayed wall-clock time. Hosts should still maintain normal clock synchronization.

These measurements describe the validation dataset at that point in time; they are evidence for the design, not permanent assumptions about BF4SW activity distribution or runtime performance.
