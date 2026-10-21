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

**Do not deploy this consolidated branch blindly.** The October 21 consolidation collects source from multiple historical branches; components require independent integration tests and a clean-host rehearsal before production rollout. Existing live installations should remain on their known-good versions until that validation is complete.

Start with [path to completion](docs/path-to-completion.md), [collector architecture](docs/collector-architecture.md), [operational schema](docs/operational-schema.md), and [live PostgreSQL schema snapshot](docs/live-schema-snapshot-2026-10-21.md).

The public website's document root is `website/site/`; the private API lives under `website/api/`. Player collector Python modules live under `player-collector/bf4ps/`. Platoon jobs live under `platoon-collector/scripts/`. Use the component's own deployment configuration; **never** commit production secrets, database passwords, runtime state, generated snapshots, or personal credentials.

## Source and migration caveat

The live database reported Alembic `0017_rank_immutable_scores` on October 21, 2026, but only migration files through `0013` were found across the surveyed remote branches. Recover and verify migrations `0014`–`0017` before claiming a reproducible fresh database installation. The schema snapshot documents the observed live structure, not an executable migration chain.

The branch inventory at [docs/branch-document-inventory.json](docs/branch-document-inventory.json) records documentation provenance. No historical branch has been deleted.
