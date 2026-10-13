# v1.0.0 clean-node deployment acceptance — planned, not executed

Operator decision: first Docker deployment on a **new, clean node** using the existing permanent `bf4_playerstats` database. D3 remains preserved and must not be dropped.

## Safety boundary
1. **Snapshot and verify restore** of permanent DB before allowing migrations. Record schema revision and exact database name from the node's own read-only connection; compare with documented `docs/database-schema-reference.md` and migration heads. No BF4SW write access.
2. **No service autostart** during install: build image, inspect file manifest, inspect installed dependencies and entrypoints, and run `alembic current` read-only before any migration. A clean node tests packaging; because the existing permanent database is already at revision 0006, `upgrade head` is expected to be a no-op, not proof of fresh-schema creation.
3. For fresh-install schema verification, use a **separate disposable database** with no production identities, then run `alembic upgrade head`, schema comparison, and rollback/restore rehearsal. Never reset the permanent database.
4. Confirm source URL points to BF4SW with SELECT-only account and destination points to BF4PS. Use separate roles for migrator, collector and website read-only where feasible.
5. Start discovery alone, with job materialization disabled by default. Verify counts, cursor and permissions. Confirm there are no unexpected jobs or writes to BF4SW.
6. Generate and persist a new UUID and collector name for this node. Egress key must represent its shared request budget. Start **one** collector only after a deliberately bounded job cohort is approved. No automatic 191k-soldier flood.
7. Exercise SIGTERM, restart, PostgreSQL disconnect/reconnect, request gate, leases, operator drain, and duplicate-identity refusal. Capture image digest, commit SHA, DB revision, job counts, request logs and final state.
8. Never run the scratch-only website exporter/API against the permanent database until reviewed and explicitly configured with read-only credentials.

## Exit criteria
- Image contains only application, migrations and the two production entrypoints; no experiments, secrets or generated player data.
- Clean-node reproducibility, schema parity, and restart/recovery proven.
- Controlled materialization, egress budget, and operator stop controls verified.
- D3 remains intact; permanent DB backup and rollback path verified.
