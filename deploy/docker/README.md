# Docker deployment — v1.0.0 release candidate

**Not yet approved for production.** The collector currently requires a hostname in `bf4ps.production_hosts.HOSTS` (tcou, kah-01, hnl-01), so generic self-hosting needs a configurable stable identity before release. Each worker needs a distinct identity and egress key. Do not run a second collector with an existing identity.

- External PostgreSQL is required; this Compose file does not create or wipe databases.
- Copy `.env.example` files to untracked `.env` files and fill secrets. Use a separate BF4SW **read-only** source account.
- Before starting services, run `docker compose -f deploy/docker/compose.yaml run --rm discovery alembic upgrade head` with a verified backup and correct target database. **Do not run migrations against BF4SW.**
- Discovery defaults to *not* materializing production jobs. The materialization cutover is an explicit operator decision; do not enable collection automatically as part of first deployment.
- Build and launch discovery separately. Collector is behind the `collector` profile and requires explicit approved host identity.
- Production image contains the application, migrations, and collector entrypoint; historical soak scripts and tests are intentionally excluded.
- Before release: clean-container build, schema fresh-install/upgrade/restore tests, multi-node identity configuration, job-materialization acceptance, graceful restart/failover, Docker health checks, and release documentation.
