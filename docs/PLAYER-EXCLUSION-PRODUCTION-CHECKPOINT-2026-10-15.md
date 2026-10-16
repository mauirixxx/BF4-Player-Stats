# Player exclusion production checkpoint — 2026-10-15 HST

## Activated identity

- `(platform, persona_id) = ('pc', 1007062617638)`; current soldier ID `46575`; name `DayWasRuined`.
- Reason code `data_integrity_anomaly`. This is a data-quality moderation action, not a verified anti-cheat finding.
- Production PostgreSQL `bf4_playerstats` at Alembic `0012_manual_verify_api`.
- Created `public.player_exclusions`, `public.player_exclusion_audit`, partial active index; inserted active exclusion and audit row. Tables installed by operator SQL, **not** Alembic; migration state remains `0012`.
- Granted SELECT on registry to BF4PS reader and manual API roles.

## Production database enforcement

Installed seven `BEFORE` triggers (all named `bf4ps_exclusion_*`):

- `soldiers`: INSERT or identity UPDATE prohibited for excluded identity.
- `collection_jobs`: INSERT or status/soldier UPDATE prohibited when new status is pending/claimed/running.
- `manual_soldier_verifications`: INSERT or identity UPDATE prohibited.
- `detailed_stats_current`, `detailed_stats_history`, `soldier_weapon_stats`, `soldier_vehicle_stats`: INSERT or UPDATE prohibited for excluded soldier.

Functions: `public.bf4ps_reject_excluded_soldier`, `public.bf4ps_reject_excluded_soldier_fk`, `public.bf4ps_reject_excluded_verification`. Tested in rolled-back transaction: identity INSERT and detailed-stat UPDATE both rejected with SQLSTATE 23514.

**Outstanding:** implement pre-HTTP worker checks on all eight collector images, prevent discovery from writing ancillary alias/source rows, test in-flight races, and integrate DB migration into authoritative Alembic history. The staged `migrations/0013b_exclusion_database_guards.sql` is **not** the same as the seven live triggers and should not be applied blindly.

## Public site

Restarted `bf4ps-leaderboard-api.service` and `bf4ps-temp-dashboard.service` with exclusion-aware SQL readers. Rebuilt community export via `bf4ps-community-export.service`. Verified origin `/bf4ps-api/global-soldier-search?q=DayWasRuined` -> HTTP 200 `{"rows":[]}`, soldier detail -> 404, and refreshed `temp-stats-data.json` contained zero occurrences of `DayWasRuined`.

**Outstanding:** comprehensive audit of all public exports, equipment catalog cross-source checks, external caches, and explicit collector pre-HTTP suppression. Historical database records retained for audit; no purge performed.

## Fleet-wide physical dispatch guard (same day)

Installed eighth trigger `bf4ps_exclusion_outbound_dispatch` (`BEFORE INSERT ON public.outbound_dispatches`), calling SECURITY DEFINER `public.bf4ps_reject_excluded_dispatch()`. It resolves the outbound job to `(platform,persona_id)` and rejects active exclusions with SQLSTATE `23514`. This protects the database-backed physical request authorization path shared by the eight existing collectors without rebuilding their images.

Validated with a rolled-back transaction: temporarily excluded a different identity with a pending job, attempted an outbound dispatch, received expected `check_violation`, rolled back, and confirmed temporary exclusion absent. Existing outbound dispatch rows were not modified. **This is an authorization-time guard, not a guarantee against requests already authorized before exclusion activation.** Collector code still needs claim-time skip, graceful exclusion handling, and immediate pre-network recheck; discovery still needs a registry filter. No collector containers were restarted.

## Discovery rollout and admin foundation

On `rnt-01`, deployed image `bf4-player-stats:discovery-exclusion-20261015` as `bf4ps-discovery`, using existing `deploy/docker/discovery.env`. Added an authoritative registry check to `bf4ps.discovery.import_aliases()` before soldier/alias/source/job mutations, including reconciliation. New container acquired discovery lock and advanced cursor `213891` -> `213893`; previous container renamed `bf4ps-discovery-pre-exclusion-20261015`, stopped with restart disabled. Image tested with excluded alias and fake destination (one registry query, zero writes). Source commit `aa3164f` is on local `rnt-01` branch `feature/exclusion-discovery-guard`; **GitHub push is blocked by HTTPS credentials on rnt-01**. Patch copied to `tcou:/tmp/bf4ps-discovery-transfer/exclusion.patch` for eventual GitHub synchronization.

Admin prototype `admin/index.html` and database-only `api/admin_moderation_service.py` were added to website development branch. Admin page is **not deployed**, all actions disabled, no authentication or HTTP mutation endpoint yet. Service has validation, transaction advisory lock, reversible exclusion/restore and audit; caller must supply authenticated authorization/CSRF/idempotency/rate limiting. Four unittest contracts pass. No purge implementation.

**Still open:** collector-side claim skip and immediate pre-HTTP checks, especially authorization-to-send race; full staged integration testing of admin operations, Alembic reconciliation, dedicated moderation DB role, auth/session/CSRF/secure deployment, full endpoint audit and restore/purge flows.
