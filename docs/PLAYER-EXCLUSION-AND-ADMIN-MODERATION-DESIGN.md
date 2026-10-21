# BF4PS player exclusion and administrator moderation

Status: **design approved in principle; implementation not yet deployed**. Priority: urgent. Created 2026-10-15 Hawaii local time.

## Incident and exact identity

The administrator requests immediate exclusion of PC persona `1007062617638` (soldier ID `46575`, last observed name `DayWasRuined`) for anomalous statistics. Identity is `(platform, persona_id)`, **never username**. No allegation is published by the service. Other anomalous scores require separate review.

## Authoritative database state

The current production database was verified at Alembic revision `0012_manual_verify_api` (not the older Stage 9C schema reference). No exclusion/blocklist table currently exists. The target soldier has one pending collection job at inspection. **Before migration implementation, reconcile the documented schema and live revision 0012, including all triggers, views, manual_api functions, FKs, and queue states.** Never assume the older `0005` reference is current.

## Required lifecycle

1. `active` exclusion registry keyed by `(platform, persona_id)`, with actor, reason code, created/updated timestamps, optional notes, audit trail and version. The registry must survive soldier/statistics deletion, renaming, rediscovery, and restoration. No public explanation or accusation.
2. Atomic operator action: authenticate/authorize admin; record exclusion and audit event; reject manual submission and refresh at the **database function** boundary; block discovery/admission; stop future scheduling; cancel pending jobs; require workers to recheck immediately before outbound request **and before persistence**. In-flight HTTP cannot always be recalled; its results must be discarded after exclusion.
3. Read visibility: all public soldier detail, global/alias search, general leaderboard, weapon/vehicle leaderboard, community aggregates, export snapshots, Discord interfaces, and cached results exclude active identities. Exclusion must be enforced at query or shared service boundary, not only client JavaScript. All platform variants checked separately.
4. Aggregate repair: invalidate or rebuild derived/cached materializations after exclusion; show separate statuses for `visibility_applied`, `collection_blocked`, `aggregates_rebuilt`, `exports_refreshed`, `verified`. Rebuilding must be idempotent, observable, and retryable; do not block admin HTTP for a large rebuild. No unnecessary global recalculation for window-function rankings that automatically recompute over filtered cohort.
5. Purge is a **separate**, more privileged, explicitly confirmed action. First inventory FK relationships and archive only permitted minimal audit evidence. Remove collected detail/history/weapon/vehicle records and pending work in a transaction-safe manner; preserve the exclusion identity and immutable moderation audit. Never blindly cascade without reviewing event and profile retention policies.
6. Restore is explicit and audited, and does not automatically recreate purged data; ordinary scheduling may resume after restore.

## Admin workflow

Search by name, historical alias or exact platform/persona; show precise identity and existing moderation state; review suspicious metrics and collection timestamps; select `Hide & Exclude`; choose reason and optionally add private notes; confirm; show each asynchronous propagation step and a retry option. Separate `Purge statistics` and `Restore` flows with stronger confirmations. Default to reversible exclusion, not deletion.

## API/security

Admin mutation endpoints require authenticated operator session, allowlisted role, CSRF protection, request idempotency key, authorization checks, audit logging, and rate limits. Read-only public API must never accept mutation flags. No arbitrary SQL from UI. Public 404 for excluded soldier pages; do not expose private moderation notes. Do not rely on client-side filtering.

## Rollout sequence / acceptance tests

- Document and introspect live schema and function definitions at revision 0012; write Alembic migration and a safe downgrade plan.
- Test migration and complete exclusion/restore lifecycle against isolated disposable database, including competing workers, queued/in-flight jobs, rediscovery, manual re-add, name changes, and retry races.
- Deploy all readers and admission guards before activating exclusions, with backwards-compatible migration ordering and rollback gates.
- Exclude PC persona `1007062617638`, verify no new jobs/collection, no public appearances or contributions, and that manual re-add fails.
- Rebuild affected materialized aggregates and regenerate snapshots, verify homepage and equipment statistics; only then consider separately approved purge.
- Add admin UI using the same audited moderation service; no direct browser-to-database writes.

## Safety

Until all admission and visibility paths are guarded, deleting a soldier row is **not a permanent ban** and can reintroduce the identity. Do not claim removal complete without end-to-end verification. Avoid taking collectors offline unnecessarily; coordinate brief drain if required for consistency.
