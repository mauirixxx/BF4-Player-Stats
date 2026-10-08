# Stage 9C — systemd host-local supervision design v1

Status: **DESIGN / STATIC REVIEW ONLY. No installation, activation, database migration, collector execution, or Battlelog requests authorized.**

## Scope and existing verified evidence

The isolated PostgreSQL 0004 test on tcou succeeded for rollback and committed abort/drain using a temporary collector table. Thirty offline tests passed. These results do **not** establish that systemd terminates any worker.

Host identities: tcou (collector plus materializer), hnl-01 (collector), kah-01 (collector). The shared watchdog lease is 20 seconds, checked by local guards at most every 5 seconds; watchdog renewals occur only after inspection. Run duration is six hours from DB-authoritative started_at, with deadline_at enforced by guards.

## Dependency direction

Each host runs a dedicated `bf4ps-stage9c-guard.service` as the safety anchor. Collector units declare:

```ini
[Unit]
BindsTo=bf4ps-stage9c-guard.service
After=bf4ps-stage9c-guard.service

[Service]
Restart=no
RuntimeMaxSec=21600
KillMode=control-group
TimeoutStopSec=15
```

On tcou only, materializer also declares the same `BindsTo=` and `After=` relationship to its local guard, and `Restart=no`. `BindsTo=` combined with `After=` is required: the dependent unit must not remain active when the guard becomes inactive, including after SIGKILL. Merely declaring `PartOf=` or `Requires=` is insufficient for this property.

Guard:

```ini
[Service]
Type=exec
Restart=no
RuntimeMaxSec=21600
KillMode=control-group
TimeoutStopSec=10
```

All guard, collector, and materializer units must have a finite runtime ceiling. `RuntimeMaxSec` is a secondary OS limit, not a replacement for DB-authoritative deadline validation. The watchdog is separately supervised and must not be able to authorize a new run merely because its process restarted.

**Not yet specified:** real `ExecStart`, `EnvironmentFile`, working directory, executable user, service credentials, ordering of collector/materializer startup and shutdown, launcher identity checks, and exact unit installation strategy. These must be documented and reviewed against the repository and real hosts before creating deployable units.

## Required failure tests (dummy units only)

1. Dummy guard active → dummy collector active; tcou dummy materializer active.
2. `systemctl kill --signal=SIGKILL` on dummy guard → dependent dummy services stop, without invoking Python stop logic.
3. Dummy guard exits nonzero → dependent dummy services stop.
4. Guard never starts → dependent dummy collector never starts.
5. Guard stops normally → dependent dummy services stop.
6. Dependent dummy services have `Restart=no` and cannot restart after guard loss.
7. Guard/runtime deadline expiration stops dependents.
8. Verify no actual BF4PS unit is installed, enabled, started, or stopped by the test.

Tests should use unique `bf4ps-stage9c-test-*` unit names, no database URL, no real run UUID, no HTTP, and should clean up only their own dummy units.

## Known safety gaps blocking activation

- Guard currently handles SIGTERM by returning success; dependency stop should occur when the guard becomes inactive, but must be proven on real systemd.
- Guard stop_units() issues asynchronous `systemctl stop --no-block`; systemd dependency wiring, not this command, must guarantee termination.
- The watchdog's identity-drift fault can prevent atomic abort+drain because drain_fleet revalidates identities. Lease expiry must still stop local processes; sticky abort policy requires separate review.
- Watchdog inspection's rolling budget currently considers post-boundary starts only; accepted pre-boundary rolling-window history requires review.
- There is no reviewed Stage 9C launcher or actual systemd dependency deployment.
- Never execute the real collector/materializer until all activation gates are explicitly approved.

## Gate to proceed

Create static systemd unit contract tests and a non-installing dummy-unit test generator. Inspect generated units with `systemd-analyze verify` where available, then request explicit operator approval before installing even dummy units on tcou. Repeat dummy fault injection on hnl-01 and kah-01 only after tcou verification.
