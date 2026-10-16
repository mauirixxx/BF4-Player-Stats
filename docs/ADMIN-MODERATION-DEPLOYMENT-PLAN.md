# BF4PS moderation console: deployment gate

## Current implementation (2026-10-15 HST)

- `admin/console.html` provides the interactive sign-in, private soldier search, active exclusion and audit views, exclude/restore confirmation and operator note fields.
- `api/admin_console_api.py` is a loopback-only HTTP server on `127.0.0.1:8767`. It requires a configured HTTPS origin, PBKDF2 password hash, session signing secret, username and dedicated database URL; it fails closed if any are absent. **It has not been started or published through Apache.**
- `api/admin_moderation_service.py` performs audited registry transitions in a caller-owned database transaction; it does not purge statistics or refresh public exports.
- PostgreSQL role `bf4ps_admin_moderation` exists as **NOLOGIN** and has narrowly scoped SELECT/INSERT/UPDATE rights on exclusion registry, SELECT/INSERT on audit, SELECT on soldiers, sequence usage. A rollback-only integration transaction validated these privileges, with zero residual test rows.
- Eight unit tests passed. No real login or HTTP mutation integration test has yet run.

## Activation gates

1. Review and harden login throttling, request limits, origin/CSRF and reverse-proxy access controls. Ensure admin UI and API are **not served from the public website** until protected.
2. Set a strong operator password on the server, store only its PBKDF2 hash (600,000 SHA-256 iterations with unique random salt); generate a separate 48+ character session secret. Do not commit secrets to GitHub.
3. Create a dedicated PostgreSQL LOGIN credential for `bf4ps_admin_moderation`, restricted by `pg_hba.conf` to tcou; store its DSN in a root-only systemd EnvironmentFile. Do not reuse website read-only or collector credentials.
4. Deploy API as an unprivileged systemd service on loopback; expose only via Apache HTTPS under `/bf4ps-admin-api/`, with a separate access policy for `/admin/` and `/bf4ps-admin-api/`. Preserve the public API as read-only.
5. Validate login failure, expired/tampered cookie, CSRF rejection, origin mismatch, invalid identities, rate limiting, audit-on-success, idempotency, restore, and permission-denied attempts on unrelated tables.
6. Exercise one **rollback-only** moderation mutation in a transaction, then one approved real test identity; verify public search, leaderboards and both JSON exporters, and make refresh explicit in the UI.
7. Document rollback (disable Apache routes and systemd service; do not delete audit/registry), enable service only after all gates pass.

## Remaining collector caveat

A registry exclusion activated after a physical dispatch permit has committed cannot recall that already-authorized request. The fleet now skips excluded jobs during claim and checks exclusions before dispatch authorization; the database dispatch trigger also blocks admission. In-flight requests and the narrow post-authorization interval are not fully fenced. Do not describe these as zero-request guarantees.

## Fleet rollout

Eight collectors run `bf4-player-stats:collector-exclusion-0012-20261015` with all three guard/source files byte-identical to mak-01. Some image IDs differ due to differing host baselines. All eight returned successful collections and zero restarts after upgrade. `rnt-01` Docker Compose `collector` image was updated and restarted under Compose; discovery remains separately running. Previous containers retained where possible. Do not run `docker compose build collector` against an older checkout: it could overwrite the exclusion image.
