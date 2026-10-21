# BF4 Player Stats — 451-Soldier, Four-Resource Distributed Milestone

**Recorded:** 2026-10-12 (Hawaii) / 2026-10-13 UTC
**Status:** PASS — bounded scratch-database validation; not a production launch approval.
**Repository checkout:** `feature/profile-collector`, baseline commit `90af400`; live parser changes initially node-local.
**Database:** `bf4ps_scratch_stage9c_d3` on `mak-db-02` (production BF4 Server Watcher database not modified).

## Verified database results

| Metric | Verified result |
|---|---:|
| Soldiers | 451 |
| PC / PS4 / Xbox One | 151 / 150 / 150 |
| Detailed collection successes | 451 |
| Weapon collection successes | 451 |
| Vehicle collection successes | 451 |
| Profile collection successes | 451 |
| Total successful resource collections | 1,804 |
| Distinct soldiers with persisted profile links | 451 |
| Missing profile links | 0 |
| Collection jobs remaining | 0 |
| Profile states other than success | 0 |
| Historical profile failure events | 399 |
| Historical weapon failure events | 1 |

The historical failure count is cumulative `collection_events` history, not current unresolved work.

## Execution

Three temporary systemd collectors (`bf4ps-450-ramp.service`) ran on `tcou`, `kah-01`, and `hnl-01`. All shared the scratch PostgreSQL database, leased collection jobs, and the existing request-rate protections. The 451-soldier cohort consists of the 450 Phase4C identities (150 per platform) plus the existing `mauirixxx` identity. The temporary ramp harness is `scripts/three_site_450_ramp.py` and is **not** a production service design.

## Profile failure investigation and fix

The initial profile parser required presentation, country/location, or explicit privacy markers. Real HTTP-200 account pages sometimes lacked all these optional markers despite containing a valid `section#user[data-user-id]` and links to the expected Battlefield soldier persona/platform. The collector had correctly resolved the soldier's Battlelog account, but the parser rejected the page.

Temporary, bounded, root-only HTML capture exposed the real account-page structure. A conservative fallback now recognizes a profile with no country information when a single structured account ID and the expected persona/platform soldier link are both present. Captured pages and synthetic negative cases validated this approach. A deployment mismatch on `hnl-01` initially left the new parser unactivated because its caller omitted the persona/platform arguments; that call was corrected.

All 451 profile states subsequently reached success. Historical failures were retained. **Raw HTML capture was disabled, its code removed, and 30 files deleted (10 per worker)** on 2026-10-12. Response-size, fingerprint, and marker diagnostics remain available on parser failure, without raw page retention.

## Validation and caveats

- Offline captured-page check: 10/10 previously rejected captures classified successfully when supplied matching identity.
- Expanded focused parser/account-resolution suite: 22/22 passed on `tcou`.
- Full suite during rollout: 423 passed, 6 failed, all in `tests/test_production_collector_daemon.py`. Those failures remain an explicit release gate; their cause has not yet been resolved.
- This milestone proves bounded multi-worker collection and recovery for the specified cohort. It does **not** yet prove a production-ready package, unattended long-duration operation, failover behavior, larger cohorts, or deployment reproducibility.
- At the time of milestone verification, live changes and the temporary ramp script were not committed to the GitHub branch. Verify and package a single immutable revision before future multi-node deployments.

## Next release gates

1. Commit and review the profile fix, diagnostic logging, and regression tests; keep temporary retry policy separate from production policy.
2. Resolve six production-daemon test failures; pass the full test suite.
3. Build a reproducible versioned package with documented configuration, migrations, service unit, and consistent node versions.
4. Run a larger controlled cohort (planned 1,800 identities, 600 per platform), then a multi-hour soak with rate-limit, recovery, and restart/failover evidence.
5. Decide on `v1.0.0` only after these gates pass, and document operational rollback and secrets management.
