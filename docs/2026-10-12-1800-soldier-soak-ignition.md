# BF4PS 1,800-new-soldier three-site soak — ignition record

Status: **RUNNING** (started 2026-10-12 22:17 HST / 2026-10-13 08:17 UTC)
Destination: **bf4ps_scratch_stage9c_d3 ONLY**. BF4SW `bf4_serverwatcher` was read using account `bf4_dashboard_readonly`; no source writes.

## Frozen population
Existing complete four-resource cohort: 451 (151 PC / 150 PS4 / 150 Xbox One). New frozen cohort: 1,800 (600 per platform), yielding 2,251 total soldiers (751 PC / 750 PS4 / 750 Xbox One). New cohort seeded 7,200 independent background bootstrap jobs across detailed, weapons, vehicles, profile. No scratch database wipe or backup was performed per operator instruction.

The ten operator-requested PC identities were verified by exact case-insensitive BF4SW alias lookup and included in the new cohort: deathdealer7520, blurrr666, yukonsunshine, team-ajax, madman0529, FooeY, mtallicLuis, Grimtorvus, S3AS0NALLY, Ocelot3377. Each resolved uniquely, and none was present in the completed 451 baseline.

Authoritative cohort manifest on tcou: `/root/bf4ps-1800-soak-manifest.json` (persona, platform, name, soldier ID). All three hosts carry matching frozen `/root/bf4ps-1800-soldier-ids.json` allowlists. The original `scripts/three_site_450_ramp.py` entrypoint and `bf4ps-450-ramp.service` service name were retained to avoid unnecessary deployment changes, but the harness now enforces 1,800 IDs, scratch DB name, existing stable worker identities, and a 12,000-attempt ceiling. The file/service names remain historical and should be renamed during release consolidation.

## Existing three-node deployment
- tcou, kah-01, hnl-01: `bf4ps-450-ramp.service` started and active.
- Normal request gate remains 5 seconds; existing production collection primitives unchanged.
- Removed `BF4PS_PROFILE_DIAGNOSTIC_RETRY_SECONDS=300` from all three systemd units and reloaded systemd. Profile retry now follows default `retry_delay_for_failure` logic.
- `Restart=on-failure`; services remain **disabled at boot**. A reboot of the operator's Windows workstation does not stop Linux services, but a reboot of a collector host will not auto-start that service.
- Source revision and deployment image not changed. Local experiment scripts are not yet committed to GitHub.

## Ignition evidence
- Dry-run source selection: 1,800 selected, 10 friends, 451 preexisting; no writes.
- Scratch seed: 1,800 complete, 7,200 jobs created.
- Read-only post-seed census: 751 PC, 750 PS4, 750 Xbox One.
- Initial live success events observed for detailed, weapons, vehicles; profile job observed running.
- Scratch DB Alembic head observed `0006_stage9c_soak_round_ledger`; older human schema reference says `0004_stage9c_supervision_runs`. **Documentation needs reconciliation to current migration chain before release.**

## Acceptance pending
Do not mark this run PASS until all 1,800 new soldiers have four persisted resource successes, per-platform/worker accounting is complete, retries and throttling are audited, and zero orphan/unresolved jobs remain. Keep historical failure events; do not conflate cumulative failures with unresolved state. Docker build and packaging follow soak acceptance.
