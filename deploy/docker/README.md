# Docker deployment — v1.0.0 release candidate

**Not yet approved for production.** New collector nodes require explicit `BF4PS_COLLECTOR_UUID`, `BF4PS_COLLECTOR_NAME`, and `BF4PS_EGRESS_KEY`. Use a stable, unique UUID/name per worker; use the **same egress key for workers sharing an external request-rate budget**. Do not run two collectors with the same identity. The old hostname mapping remains only for backward compatibility.

- External PostgreSQL is required; this Compose file does not create or wipe databases.
- Copy `.env.example` files to untracked `.env` files and fill secrets. Use a separate BF4SW **read-only** source account.
- Before starting services, run `docker compose -f deploy/docker/compose.yaml run --rm discovery alembic upgrade head` with a verified backup and correct target database. **Do not run migrations against BF4SW.**
- Discovery defaults to *not* materializing production jobs. The materialization cutover is an explicit operator decision; do not enable collection automatically as part of first deployment.
- Build and launch discovery separately. Collector is behind the `collector` profile and requires explicit stable identity configuration.
- Production image contains the application, migrations, and collector entrypoint; historical soak scripts and tests are intentionally excluded.
- Before release: clean-container build, schema fresh-install/upgrade/restore tests, multi-node identity configuration, job-materialization acceptance, graceful restart/failover, Docker health checks, and release documentation.
