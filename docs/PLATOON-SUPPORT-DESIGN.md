# BF4PS — Verified Battlelog Platoons: Design Contract

**Status:** DESIGN ONLY — no migrations, collectors, UI deployment, or membership import authorized by this document.
**Created:** 2026-10-18
**Source of truth:** official Battlelog platoon member roster, NOT matching tag text.
**Related:** `docs/PERFORMANCE-OPTIMIZATION-ROADMAP.md`, `docs/LIVE-POSTGRESQL-SCHEMA-2026-10-17.md` (live schema snapshot on documentation branch), collector repository `docs/database-schema-reference.md`. Verify production schema before implementation.

## 1. Goal and boundaries

Add Battlelog-recognized platoons as first-class entities on BF4 Player Stats, each with a dedicated page, aggregate statistics computed from already-collected soldier records, member roster, and platform-aware links. Import platoons by official Battlelog view/members URL or numeric platoon ID. Support multiple official platoons per Battlelog account and soldier. Do not infer membership from a four-character clan tag or similar name.

**Identity rule:** `platoon_id` (Battlelog ID, e.g. `754443074295858477`) is authoritative for a platoon; BF4 soldier identity is `(platform, persona_id)`, not player name. Store the numeric-looking Battlelog platoon ID as a 64-bit integer (range validation) or text if the live source proves IDs can exceed signed bigint. Never use floating-point JavaScript numbers for 18–19-digit IDs; transport as strings.

**Platform rule:** PC, PlayStation, and Xbox are supported, including mixed-platform rosters and aggregated views. The roster may expose other platforms/games (Xbox 360, BF Hardline); store source evidence but only map supported BF4 identities. Platform must never be inferred from tag or account name.

## 2. Battlelog evidence, 2026-10-18

Fetched `https://battlelog.battlefield.com/bf4/platoons/members/754443074295858477/` successfully from tcou (HTTP 200, 480,152-byte HTML response). The page identifies **[Wire] Team Wired**, includes 200 `club-member expanded` elements, profile links (e.g. `/bf4/user/FooeY/`), avatar URLs, platform indicators, and embedded `personaBoxes` JSON with `platform`, `game`, `personaId`, `personaName`. These observations are evidence of parseable information, **not proof that all members/personas are included**: determine whether pagination, lazy loading, additional requests, hidden/removed users, or account-to-persona associations require further retrieval. Do not assume the account-level `rel` attribute on avatar links is a BF4 persona ID.

One account may have multiple platform soldiers. Main platoon shown on a user profile is a display preference and **not** a limit on membership; do not discard non-main memberships. Maximum of nine memberships is an operator observation, not a hardcoded DB constraint until verified.

## 3. Proposed relational schema (migration design; NOT applied)

- `platoons`: `platoon_id BIGINT PRIMARY KEY`; official name, tag, canonical URL, description/emblem URL if available, discovered/last_checked timestamps, source state (`active`, `unavailable`, `private`, `error`), roster fetch status and provenance. Optional creation/deletion dates only if Battlelog provides evidence.
- `platoon_memberships`: composite unique `(platoon_id, platform, persona_id)` for **resolved BF4 soldier membership**; FK to platoons and FK to existing soldier identity using **actual live schema keys**, plus first_seen, last_confirmed, status (`confirmed`, `unverified`, `former`), source URL, source observation ID. Allow one soldier in multiple platoons.
- `platoon_roster_accounts`: `(platoon_id, battlelog_account_id)` unique when account ID is present, account username, first/last seen and roster evidence. Retain accounts that have no resolvable BF4 soldier yet. Do not use username as authoritative ID.
- `platoon_roster_personas`: evidence mapping roster account to BF4 `(platform, persona_id)`, with BF4 game/platform classification and resolution status. This separates what Battlelog actually says from a membership inference. Promotion to `platoon_memberships` requires verified association rules.
- `platoon_sync_runs` or `platoon_roster_observations`: attempted/finished time, result, roster count, page completeness, parser version, HTTP status/error class, content checksum. Record partial snapshots; **never expire members from incomplete/failed fetches**.
- Optional `platoon_primary_preferences` only if primary membership can be independently proven and the exact semantics are established. Do not force exactly one primary platoon in the membership table.

Indexes: `platoon_memberships(platform, persona_id)` for soldier dossier lookup; `platoon_memberships(platoon_id, status, platform)` for roster and aggregates; unique roster-account and roster-persona keys; `platoons(tag)` nonunique for search only. Use appropriate foreign keys and avoid duplicating large weapon/vehicle tables. Before migration: compare this proposal with live PostgreSQL catalog and collector Alembic authority; produce explicit migration, rollback, and index-cost assessment.

## 4. Import workflow and safety

1. User submits official Battlelog platoon view/members URL or ID; normalize and validate host/path/ID; no arbitrary URL fetching (SSRF protection). Do not accept tag-only identity.
2. Fetch with bounded concurrency, per-egress pacing, timeouts, respectful retry/backoff and clear failure classification. One-time import followed by low-frequency refresh; **no extra Battlelog requests per website page view**.
3. Parse platoon metadata, roster accounts, BF4 persona boxes and platforms; save source provenance and raw evidence in bounded debug/audit storage (no public leaking of private account data).
4. Resolve account/persona relationships and match existing soldier rows by platform + persona ID; queue *missing* soldier identities for admission via the existing collector policy, never bypass the global request budget or duplicate soldier rows.
5. Transactionally upsert evidence and confirmed memberships. Incomplete roster snapshots must not trigger mass membership removals; require consecutive complete observations and an operator-configurable grace period before marking former.
6. Expose sync freshness, counts (official accounts, resolvable BF4 soldiers, collected members, unavailable/unresolved), and any uncertainty in the UI. Support manual recheck with cooldown and audit log. No manual override that silently claims Battlelog-verified membership.

## 5. Aggregate statistics — avoid double counting

Platoon pages must compute stats from **distinct** confirmed soldier identities with collected data. One soldier belonging to multiple platoons contributes once **to each platoon**, but never twice **within the same platoon**. No summing preaggregated platoon totals to create a global community total (would double-count overlapping soldiers). Distinguish PC, PlayStation, Xbox, and ALL with filters; do not collapse separate personas of one Battlelog account unless a later, explicitly labeled account-combined view is approved.

Initial aggregate candidates: collected members, kills, deaths, K/D, score, playtime, wins/losses, weapon/vehicle totals and platoon equipment leaderboards, **only where authoritative source fields exist**. Derive ratios from summed numerators/denominators, never average individual ratios. Define missing-data and last-collected semantics; members who have never been collected count toward roster totals but not collected-stat sums.

For millions of soldiers, prefer bounded platoon-member joins and optional incremental/materialized platoon summaries, with cache invalidation on membership changes and collection completion. Do not multiply per-member rows by joining weapons and vehicles together before aggregating. Precompute only after measuring with representative platoon sizes.

## 6. UI

- New `/platoons.html`: searchable list and official Battlelog URL/ID add flow, platoon detail `/platoon.html?id=<platoon-id>` (or stable route), verified name/tag, platform filters, membership coverage and freshness, aggregate cards, member roster and soldier dossier links. If add requires authorization or budget controls, require authenticated operator or rate-limited admission; public read remains available.
- Soldier dossier: split existing **Known Aliases** panel into two responsive halves, **Known Aliases** and **Platoons**, stacking on narrow screens. Show *all* verified platoons with links, mark main only when proven; indicate unresolved/last-seen membership without treating an identical tag as proof.
- Main header: move **Admin** into the current **Soldiers** position; move **Soldiers** into the current **Community Stats** position; insert **Platoons** between Soldiers and Community Stats. Intended order: **Leaderboards · Equipment View · Admin · Soldiers · Platoons · Community Stats**. Preserve admin authorization/visibility and responsive wrapping. Header changes are designed, **not yet deployed**.
- Avoid an extra catalog loading spinner for platoons; cache small reference data statically where appropriate, with explicit refresh/freshness semantics.

## 7. Staged milestones and acceptance

**P0 Design approval:** review this document and existing live schema; settle whether account-level roster membership authorizes each linked BF4 persona, what counts as a complete roster, primary platoon evidence, and public add permissions.

**P1 Read-only Battlelog parser spike:** one official platoon (Team Wired) with representative accounts and platforms; validate full roster completeness, page navigation, account IDs vs persona IDs, and false positives. No writes to production. Store fixtures and unit tests.

**P2 Migration in isolated test DB:** additive schema only, Alembic migration, uniqueness and FK tests, partial-fetch safety, multi-platoon and cross-platform tests. Document schema before application.

**P3 Import pipeline:** bounded scheduling, provenance, account-persona resolution, safe retries and controlled missing-soldier admission. Pilot a few operator-approved platoons.

**P4 API and UI:** platoon page, dossier panel, global header, aggregates with explicit missing-data labels, platform filters, links.

**P5 Production rollout:** schema check, migration backup/rollback plan, slow-query budget, no extra requests on page load, index/replication monitoring. Expand platoons gradually.

### Deliberate non-goals for this phase

- Importing all 6+ million PC soldiers as a prerequisite.
- Using tags to infer membership.
- Treating account avatar IDs as soldier persona IDs.
- Assuming every Battlelog member has a currently accessible soldier.
- Claiming all membership is current based on one partial or failed fetch.
- Building a Discord platoon feature or cross-platform account merge before the core membership model is validated.

## 8. Six-million-soldier scalability (separate workstream)

Before bulk import, distinguish identity-only rows from full statistics collection; forecast rows, index sizes, storage and replication WAL for each stage; admission pacing and backlog ETA; queue fairness and API freshness; HA replica lag; partitions or summary tables only if measured workload warrants. Do not couple a platoon schema migration to a mass soldier import.

## 9. Operator decision and verified overview data (2026-10-18)

**Decided:** Membership belongs to the individual **soldier persona**, keyed by `(platform, persona_id)`, not the Battlelog account. The official roster remains the sole membership authority. Account-level evidence can help resolve personas but does not by itself prove that every persona on the account is a member. This supersedes the earlier undecided account-versus-persona question.

**Simplify the MVP:** Start with `platoons` and `platoon_memberships` as the two essential tables; include source evidence, sync timestamps, and status fields on these rows. Separate account/roster-evidence and sync-history tables are **optional** if a read-only parser spike shows they are necessary for safe resolution and failure recovery. No need to store platoon IDs as an array on the soldier row; query the join table for the dossier.

**Official overview observed:** `https://battlelog.battlefield.com/bf4/platoons/view/754443074295858477/` returned HTTP 200, 431,495 bytes. Team Wired: tag Wire; created 2014-08-18; website `http://team-wired.net/`; member count 200; rank 50; score 13,751,416; skill 865; K/D 4.230; time 5184h 50m; presentation HTML available. Score tooltip: BF4 13,608,607 + Hardline 142,809. Skill tooltip: BF4 1000, Hardline 730. K/D tooltip: BF4 4.27, Hardline 2.8. Time tooltip: BF4 5095h 27m, Hardline 89h 23m. **Official aggregate figures mix games** and represent Battlelog platoon progression/member contribution, not necessarily a sum of each member's lifetime BF4 statistics. Preserve official figures and provenance separately from BF4PS-calculated BF4-only totals. Do not sum skill/KD values across games.

**Collector proposal:** one dedicated platoon worker with its own egress IP, bounded polling, parser/version checks, verification timestamps, and controlled retries. It collects overview and official roster snapshots; does **not** compute or fetch individual soldier statistics. Keep requests inside a separately documented Battlelog traffic budget and do not increase overall traffic without explicit operator approval. Website serves stored data; no synchronous Battlelog calls on page loads.

**Pending validation:** parse roster account-to-persona associations, verify all 200 entries and BF4 platform membership, define complete-snapshot semantics, and determine whether the official aggregates update for inactive platoons. No schema changes or production import until those checks are done.

## 10. Outstanding decisions for operator

1. Who may add a platoon: authenticated admin only, or rate-limited public submission?
2. **Resolved identity policy:** individual soldier persona, not account. Verify official per-persona membership evidence before inclusion; never infer all account personas are members.
3. Former members: retain historical memberships with dates and exclude them from current aggregates by default?
4. Which collective stat cards matter most for initial launch? Default: roster/collected coverage, kills/deaths/KD, score, playtime.
