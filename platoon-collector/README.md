# Platoon collector

The canonical platoon scripts live in `scripts/`. The deployed `mak-05` and `hnl-03` timer jobs invoke `scripts/platoon_alternating_scheduler.py` every 15 seconds using their local service definitions. Both sites should deploy the **same versioned script set**, while preserving site-specific service units, environment, credentials, and runtime state outside Git.

## Verification

Historical test results and removed harness inventory are documented in `../docs/TEST-AND-VALIDATION-HISTORY.md`. Compare `sha256sum scripts/*.py` across hosts after deployment. `systemctl is-active bf4ps-platoon-alternating.timer` should report `active`; the corresponding oneshot `.service` may legitimately report `inactive (dead)` between timer firings.

## Deployment caution

Never copy `.env` files or local backup scripts into the repository. Take a backup of each host's current scripts, stage the verified files, and atomically replace each script. Do not restart the timer or run concurrent scheduler instances during deployment. Validate the next scheduled executions and compare file hashes. The two hosts may have different Git HEAD values until their checkouts are separately reconciled; on-disk hashes are the definitive code parity check.

`export_platoon_site.py` and `platoon_submit_api.py` include newer consolidated features (emblem caching and manual soldier refresh) that were not on both deployed hosts before consolidation; these are preserved intentionally rather than replaced with older deployed versions.
