> **2026-10-25 update:** The nine production **player-statistics collectors** were rebuilt from GitHub `main` commit `6589a7e` and their running Git revision labels, 4-second pacing, exclusion-aware claims, module checksums, and successful collections were verified. PostgreSQL Alembic head was observed at `0018_distributed_rank_queue`. Source-parity audit for website, Discord bot, platoon/discovery/ranking services, byte-identical image publication, full integration testing and sustained soak remain open. See [current production checkpoint](PROJECT-CURRENT-STATE.md).

# BF4PS — Path to Completion

**Consolidation date:** 2026-10-21. **Status:** Working master plan, not a claim that every item is implemented or production validated.

This document collects project milestones, outstanding designs, operational risks and future ideas discovered in the historical 115-branch survey. Detailed original documents remain in docs/, including alternate historical revisions under docs/history/branch-variants/. The provenance index is branch-document-inventory.json. Do not treat historical design documents as proof of deployed behavior.

## 1. Consolidation and release integrity

- [x] Inventory remote branches and recover Markdown documentation without deleting historical branches.
- [x] Assemble website, player collector, platoon collector and planned Discord bot directories on a separate consolidation branch.
- [x] Compare live PostgreSQL catalog against documentation; capture columns, indexes and constraints.
- [x] Recover **Alembic 0014–0017** from the deployed `mak-01` collector; SHA-256 checksums match the deployed source. The complete 0001–0017 revision chain is now present.
- [ ] Run a clean-database migration rehearsal and verify the resulting catalog against production before advertising reproducible deployment.
- [ ] Compare component sources against **deployed** code on tcou, player collector nodes and platoon workers. Nine player-statistics collectors passed SHA-level source verification on October 25, but tcou website/API, Discord HA, mak-05/hnl-03 platoon collectors, discovery and ranking workers remain on separate deployed branches/images and require independent audits.
- [ ] Resolve imports, paths, dependency installation and deployment configuration after the new directory layout. Perform clean-host smoke tests and new release verification. Historical test harnesses were removed from the deployable tree after their purpose and actual results were documented in `docs/TEST-AND-VALIDATION-HISTORY.md`; a passing fresh integration suite is still required.
- [x] Fast-forward consolidated source to `main` (commit `db98cb3`), with history preserved.
- [ ] Finish CI, secret scanning, reproducible builds and component release validation; prepare a v1.0.0 GitHub draft until gates pass.
- [ ] Retain historical branches until a deliberate, separately approved archival/cleanup plan. No mass deletion.

## 2. Player statistics collector

- [x] Distributed collection architecture, jobs, request gates, identity aliases, detailed/weapon/vehicle/profile collection, physical dispatch budget and retry design developed in historical branches.
- [ ] Validate the consolidated player collector against the **nine-node** live fleet; verify Docker build, configuration and systemd restart behavior.
- [ ] Confirm PostgreSQL admission, global/egress pacing, rolling 4,800/hour budget, manual refresh priority ceiling, exclusion trigger, profile privacy and job-fencing behavior against production.
- [ ] Run extended soak, crash/restart and database failover tests with measurable throughput, retry and data integrity results.
- [ ] Keep separate persona/platform identities authoritative; support manually verified cross-platform account associations and clearly labeled combined views later.
- [ ] Confirm BF4SW read-only discovery import, duplicate aliases, rename history, console profile username mismatches and complete multi-platform identity coverage.

## 3. Platoon collection

- [x] Shared per-platoon UUID lease table deployed; mak-05 and hnl-03 both completed live platoon jobs on October 21.
- [ ] Run sustained two-node concurrency/lease-expiry/stale-owner/failover soak and verify no duplicate import or stale finalization.
- [ ] Audit **soldier-to-platoon discovery** separately for multi-host claim safety; the shared lease currently protects platoon request/refresh imports, not necessarily discovery jobs.
- [ ] Validate independent Battlelog request pacing and retry behavior across both sites, including 404/blocked platoons and excluded soldiers.
- [ ] Admin-only queued platoon search, refresh/reprioritization with authentication, CSRF and auditing.
- [ ] Platoon membership history, aggregation/deduplication, combined platoon statistics, manual associations and future platoon-specific dashboards.
- [ ] Reconcile deployed local modifications/backups with Git before release.

## 4. Website and API

- [x] Website, private manual-request gateway, read-only leaderboard API and admin source recovered from website/performance branches.
- [ ] Confirm source parity with the **deployed** website, including recent October 18–20 indexed rankings, equipment Top 10, vehicle-family aggregation, admin fixes and profile links.
- [ ] Finish no-migration indexed player search parity for weapon kills/KPM/accuracy and vehicle kills/KPM, preserving rank, percentile, ties, division and alias behavior. Earlier weapon KPM parity failed; require a passing re-test.
- [ ] Benchmark uncached/cached p50/p95 response times, browser parse/DOM/memory, page sizes and concurrency; preserve bounded top-N fast paths and safe fallbacks.
- [ ] Audit equipment population freshness, immutable score/rank generation, background backfill, transaction parity and excluded-soldier filtering.
- [ ] Finish administrator artwork replacement UX, HUD/fancy asset mappings, cache invalidation, security checks and moderation workflows.
- [ ] Repair and validate platoon admin dashboard/API errors and production deployment/rollback steps.
- [ ] Review admin authentication, least privilege, session handling, CSRF, OAuth plans, logging and credential rotation.

## 5. Discord bot — future component

- [ ] Define read-only Discord integration architecture, deployment identity and API/database permission boundary.
- [ ] Design slash commands such as /stats with platform disambiguation, alias history, soldier dossiers, optional platoon lookup and embeds.
- [ ] Specify caching, rate limits, outages, guild permissions, moderation and privacy handling.
- [ ] Implement and test independently of production collection workers.

## 6. Operations and roadmap

- [ ] Publish complete schema migration chain and periodic catalog-drift checks against PostgreSQL primary.
- [ ] Document HA failover, backups/restore, disaster recovery, collector-node registry, monitoring/alerting and release rollback.
- [ ] Preserve historical benchmark and soak evidence without implying older checkpoints are current.
- [ ] Evaluate additional collector/platoon nodes only after shared pacing, safety and observability are validated.
- [ ] Consider player comparison tools, combined cross-platform profiles, more platoon analytics, richer artwork and API consumer integrations.

## Primary source documents

- docs/ROADMAP.md — October 19 roadmap; deployment status of hnl-03 platoon worker is superseded by October 21 verification.
- docs/PERFORMANCE-OPTIMIZATION-ROADMAP.md — full performance and product backlog.
- docs/PLATOON-SHARED-LEASE-DESIGN.md and docs/PLATOON-DISTRIBUTED-WORKERS-20261021.md — lease architecture and rollout.
- docs/collector-architecture.md, docs/phase5b-production-scheduling-capacity-design.md and docs/runtime-budgets.md — collector scheduling.
- docs/database-schema.md, docs/operational-schema.md and docs/live-schema-snapshot-2026-10-21.md — database contracts and current observed catalog.
- docs/branch-document-inventory.json — all discovered document paths, preferred sources and archived content variants.

**Acceptance criteria for a stable v1.0.0 release:** documentation complete, no secrets, runnable clean-checkout component builds/tests, recovered migrations through live revision, production-source parity reviewed, and a rollback plan. Until then, the GitHub release remains a draft and must not be described as a verified production installer.
