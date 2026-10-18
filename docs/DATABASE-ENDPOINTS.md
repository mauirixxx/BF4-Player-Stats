# BF4PS PostgreSQL connection topology

Operator-confirmed 2026-10-17:

- **Application DNS endpoint:** `db.bf4statusbot.com` for **all database reads and writes**, including the website and platoon collector. Do not configure clients with physical database node names or IP addresses.
- **Current primary:** `mak-db-02`. Verified locally using PostgreSQL `pg_is_in_recovery() = false`.
- **Current replica:** `mak-db-01` (operator confirmed read-only). Never target this node directly for application writes.
- DNS from `tcou` resolves `db.bf4statusbot.com` to `192.168.10.78` at this checkpoint; this address is observed, not a hardcoded application configuration.
- On failover, validate DNS target and PostgreSQL write role before enabling new write workloads.
- **Production database:** `bf4_playerstats`. Use a dedicated least-privilege platoon collector role with DML only on platoon tables and SELECT on explicitly required identity tables. Administrative migrations are performed separately as postgres on the primary.
- `mak-05` is the sole planned platoon collector; its service must use the DNS endpoint, not `mak-db-02`.

## Verification

From a configured DB client, check `SELECT current_database(), pg_is_in_recovery(), inet_server_addr();` and verify the target is the expected primary. Never expose credentials in logs.
