# Stage 9C D2 — three-site eight-worker two-hour synthetic soak checkpoint (2026-10-11)

**Result: PASS for synthetic D2 claim/release endurance only. Production HOLD.**

## Reproducibility and boundaries

- Git revision: `7ac88fdf81a83f7d20ed7a8f1d1e24cb21b93103` (`fix/stage9c-t4-inspector-lease-expiry`).
- Run ID: `d2soak8_20261011_c`.
- Manifest semantic SHA-256: `b4138a14777722941ee4b917dcf6dc7df197ce831bd90e1b76aedc92c87971b4`.
- Manifest file SHA-256: `e4f3a9e1373f35157fceee31b849630eedd96608c1359f3597660d7fdcaf5618`.
- State file SHA-256: `9de1ed075d3dfd549627b4ce711a3121506e3f624c9d40cb1d77c71e0137b6cb`.
- 64 synthetic D2 jobs, eight workers, 30-second leases, 0.5-second polling, two-hour bounded host launchers, no external HTTP.
- All three hosts independently passed D2 database identity and manifest/state/intent validation. Scratch database only; no production services or schema changes.

## Per-worker evidence (read directly from saved JSON reports)

| Host | Worker | Claims | Releases | Errors | Lease losses | Empty polls | HTTP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tcou | 0 | 14264 | 14264 | 0 | 0 | 0 | 0 |
| tcou | 1 | 14264 | 14264 | 0 | 0 | 0 | 0 |
| tcou | 2 | 14264 | 14264 | 0 | 0 | 0 | 0 |
| kah-01 | 0 | 10819 | 10819 | 0 | 0 | 0 | 0 |
| kah-01 | 1 | 10823 | 10823 | 0 | 0 | 0 | 0 |
| kah-01 | 2 | 10831 | 10831 | 0 | 0 | 0 | 0 |
| hnl-01 | 0 | 11233 | 11233 | 0 | 0 | 0 | 0 |
| hnl-01 | 1 | 11235 | 11235 | 0 | 0 | 0 | 0 |
| **Total** | **8** | **97733** | **97733** | **0** | **0** | **0** | **0** |

All eight reports had `status=complete`, `duration_seconds=7200`, matching run/manifest identities. Earliest start: 2026-10-11 09:53:53.924911 UTC; latest finish: 2026-10-11 11:53:57.072922 UTC. All eight workers overlapped for essentially the entire two hours. Host launchers independently reported PASS.

## Database closure

Post-run coordinator verification returned `jobs=64, claimed=0, unclaimed=64`. Coordinator cleanup then returned zero for `collection_events`, `collection_jobs`, `collection_state`, `collectors`, and `soldiers`. Historical report/heartbeat files remain on their respective hosts under `/root/bf4ps-d2-tests/soak8-c-<hostname>/`. The original manifest/state/intent files remain available for audit.

## What this does not prove

This synthetic exercise made **zero physical HTTP dispatches** and cannot establish the global hard limit of 1296 actual HTTP dispatches in any rolling 3600-second window. It also does not establish a non-bypassable outbound boundary, retry/redirect attempt accounting, delayed-send fencing, safe gateway failover, or independent network-level dispatch evidence. The physical-send NO-GO decision remains unchanged. Refer to `docs/stage9c-d2-physical-network-boundary-decision-gate-2026-10-10.md` and `docs/stage9c-d2-send-boundary-uncertainty-design-2026-10-10.md`.

## Next safe gate

Create an offline proof-obligation matrix linking each physical-send invariant to code, adversarial tests, independent evidence, and unresolved gaps. Do not enable external HTTP or alter host networking without separate operator approval.