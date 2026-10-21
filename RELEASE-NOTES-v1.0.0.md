# BF4 Player Stats v1.0.0 — release draft

**Status: draft; NOT YET VERIFIED FOR NEW PRODUCTION DEPLOYMENTS.**

The first consolidated project-wide release brings the BF4 Player Stats source into one `main` branch instead of requiring users to assemble historical development branches.

## Included

- `website/`: public BF4 player-statistics website, read-only API, admin tooling, and deployment examples.
- `player-collector/`: distributed player-statistics collector, discovery, scheduling, request budgets, Docker/systemd examples, and Alembic revisions `0001` through `0017`.
- `platoon-collector/`: platoon roster collection and discovery scripts, shared-lease logic, and operations guidance.
- `discord-bot/`: documented **future component only**; no runnable Discord bot is included.
- `docs/`: schema references, architecture, design decisions, operational guidance, historical milestones and roadmap.
- `INSTALL.md`: component installation overview, safety boundaries and known missing turnkey deployment pieces.

## Verified during consolidation

- Consolidated source promoted to `main` by fast-forward without rewriting prior history.
- All 17 Alembic revision files are present; revisions `0014`–`0017` were recovered from a deployed checkout and byte-for-byte checked.
- All 80 remaining Python source files passed syntax parsing in the consolidated checkout.
- The eleven platoon worker Python scripts were synchronized byte-for-byte across `mak-05` and `hnl-03` at the earlier `24db633` deployment; their timers reported successful post-deployment execution.
- Git whitespace validation passed. No obvious tracked private-key or `.env` files were found in the checked patterns.

These are limited checks, **not** proof of a clean-host production installation. See `docs/TEST-AND-VALIDATION-HISTORY.md`.

## Known limitations and release blockers

- Fresh isolated PostgreSQL migration rehearsal from `0001` to `0017` is pending.
- Deployed website and player-collector source parity has not been fully verified.
- Clean-host dependency installation, Docker build and end-to-end service/API validation remain pending.
- Apache/PHP website provisioning and platoon service deployment are not yet turnkey installers.
- Removed historical tests are recoverable from Git history, but do not constitute an active regression suite.
- The Discord bot is planned, not implemented.

## Installation and upgrades

Read `INSTALL.md` **before** deployment. Do not run migrations against the BF4 Server Watcher database or against existing production databases without explicit target verification, backups and an approved rollback plan. This release does **not** automatically deploy or migrate any running BF4PS installation.

## Historical branch retention

Historical branches have **not** been deleted. Removed staging/test artifacts can be recovered from prior commits, including `ab9419c`. See `docs/branch-document-inventory.json` and `docs/path-to-completion.md`.

## Before publishing as stable

Complete and document clean database migration, fresh-host startup, website/player-collector source parity, production-safe smoke tests, and rollback verification. Publish only after those checks pass.
