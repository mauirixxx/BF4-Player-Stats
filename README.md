# BF4 Player Stats

BF4PS collects Battlefield 4 player statistics, platoon membership and historical identity data into PostgreSQL and serves a public statistics website. This repository is organized by **deployable component**, rather than by the historical feature branch used to develop it.

## Project layout

| Directory | Description |
| --- | --- |
| [website/](website/) | Apache/PHP frontend, Python APIs, admin dashboard and website deployment assets |
| [player-collector/](player-collector/) | Distributed BF4 player-statistics collectors, scheduling, Docker/systemd examples, PostgreSQL/Alembic migrations |
| [platoon-collector/](platoon-collector/) | Platoon roster and soldier-to-platoon discovery workers, PostgreSQL shared UUID lease/fencing |
| [discord-bot/](discord-bot/) | **Planned** Discord integration; no production bot code yet |
| [docs/](docs/) | Architecture, operational guidance, historical checkpoints, design notes and roadmap |

## Getting started

For component prerequisites, source layout and release gates, read the [installation guide](INSTALL.md).

**Do not deploy this consolidated branch blindly.** The October 21 consolidation collects source from multiple historical branches; components require independent integration tests and a clean-host rehearsal before production rollout. Existing live installations should remain on their known-good versions until that validation is complete.

Start with [path to completion](docs/path-to-completion.md), [collector architecture](docs/collector-architecture.md), [operational schema](docs/operational-schema.md), and [live PostgreSQL schema snapshot](docs/live-schema-snapshot-2026-10-21.md).

The public website's document root is `website/site/`; the private API lives under `website/api/`. Player collector Python modules live under `player-collector/bf4ps/`. Platoon jobs live under `platoon-collector/scripts/`. Use the component's own deployment configuration; **never** commit production secrets, database passwords, runtime state, generated snapshots, or personal credentials.

## Source and migration caveat

The live database reported Alembic `0017_rank_immutable_scores` on October 21, 2026. Migration files `0014`–`0017` were recovered from the production player-collector checkout on `mak-01` and verified byte-for-byte against the source. All `0001`–`0017` migration files are now present, but a clean-database migration rehearsal is still required before claiming a reproducible fresh installation.

The branch inventory at [docs/branch-document-inventory.json](docs/branch-document-inventory.json) records documentation provenance. No historical branch has been deleted.

## Historical testing artifacts

One-off test harnesses and staging-only pages are excluded from the deployable tree. See [validation history](docs/TEST-AND-VALIDATION-HISTORY.md) for their purposes, actual recorded results, and recovery from Git history. This cleanup does not replace clean-install verification.

## Current production collector release (2026-10-25)

The nine distributed BF4PS statistics collectors run the source from GitHub commit `6589a7e`, with 4-second per-egress spacing and exclusion-aware claims, under the existing shared 4,800/hour physical dispatch budget. See [current state](docs/PROJECT-CURRENT-STATE.md) and [collector release procedure](player-collector/deploy/docker/PRODUCTION-RELEASE.md). The website, Discord bot, platoon and ranking services still require separate deployed-source parity checks; do not assume they share this release.
