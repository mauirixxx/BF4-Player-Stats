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

## tcou real-systemd dummy SIGKILL result — 2026-10-07

Operator executed the staged three-unit dummy test on tcou (all ExecStart=/usr/bin/sleep 3600). All three were active before injection. At 20:13:56 local journal time, `systemctl kill --kill-whom=main --signal=SIGKILL bf4ps-stage9c-test-guard.service` killed the guard's main process (PID 851608, status=9/KILL). systemd immediately logged stopping both dependent units. Three seconds later: guard `failed/failed`, `MainPID=0`, `Result=signal`; collector and materializer each `inactive/dead`, `MainPID=0`, `Result=success`. Cleanup removed all three unit files; final LoadState=not-found and ActiveState=inactive for each. Two `reset-failed` warnings for unloaded dependents were harmless.

**PASS limited to:** tcou dummy-unit guard SIGKILL dependency propagation. Not evidence of real BF4PS container or collector shutdown, other failure modes, or other hosts.

## Production deployment direction (proposal, not authorization)

Prefer one versioned Docker image with role-specific collector/materializer/watchdog/guard commands, deployed alongside the existing BF4SW fleet where appropriate. Keep BF4PS separate from BF4SW databases and releases. Host-level systemd should supervise Docker service lifecycle and guarantee dependent container stop on guard loss; verify Docker stop/kill and restart policies using dummy containers before live deployment. Stage 9C's six-hour lease/deadline is a trial authorization, not a permanent production operating model. Production requires a separately designed renewal and recovery policy, schema/role permissions, backups, observability, and explicit go-live approval.

## Next controlled tests — tcou, then remote hosts

The tcou SIGKILL experiment passed; it is not a substitute for testing other exit modes. Repeat only with isolated `bf4ps-stage9c-test-*` dummy units, with no database credentials and no real BF4PS services.

1. **Normal guard stop:** start three dummy units, `systemctl stop bf4ps-stage9c-test-guard.service`, confirm both dependents become inactive/dead and MainPID=0.
2. **Unexpected guard exit:** the SIGKILL experiment already demonstrates an unexpected signal exit; separately test a nonzero exit only after designing a dummy guard that exits nonzero on command.
3. **Runtime expiration:** shorten the *dummy-only* guard RuntimeMaxSec to a controlled duration, start all three promptly, confirm guard expiration causes both dependents to stop. Distinguish guard runtime expiration from the dependents' own runtime limits.
4. **Cleanup:** stop all test units, remove only their unit files, daemon-reload, confirm LoadState=not-found and ActiveState=inactive. A reset-failed warning for already-unloaded units is harmless.

Before installing dummy units on hnl-01 or kah-01, separately confirm that systemd is available, `/usr/bin/sleep` exists, and no test units with those names are present. Do not deploy real collectors.

## Roadmap boundary

The six-hour Stage 9C trial is documented. A five-step production path (Stage 9C completion, Docker packaging, production DB preparation, shadow deployment, controlled go-live) is **a proposal, not a previously approved end-to-end implementation plan**. Production Docker lifecycle supervision, database migration, and permanent renewable lease behavior require separate design and operator approval.
