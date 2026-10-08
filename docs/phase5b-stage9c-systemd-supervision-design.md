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

## tcou normal guard stop result — 2026-10-07

Operator reinstalled the three isolated dummy units, confirmed all active/running (guard PID 855976, collector 855981, materializer 855982), then executed `systemctl stop bf4ps-stage9c-test-guard.service`. At 20:25:38 tcou journal time, systemd stopped both dependents as part of the guard stop transaction, then stopped the guard. Two seconds later all three were inactive/dead with MainPID=0 and Result=success. Operator stopped any remaining test units, removed the three test unit files and ran daemon-reload without reported errors. No post-cleanup LoadState check was provided for this run.

**PASS limited to:** tcou dummy-unit normal guard stop dependency propagation. No live BF4PS workload was used.

## tcou dummy guard runtime expiration result — 2026-10-07

Operator confirmed no dummy units loaded, installed the three previously generated dummy services, and changed only the installed guard's `RuntimeMaxSec` from 90 to 20 seconds. `systemd-analyze verify` returned no errors. `systemctl show` confirmed guard RuntimeMaxUSec=20s, collector/materializer RuntimeMaxUSec=1min 30s, and Restart=no for all. All three started active at 20:29:20 tcou journal time. At 20:29:40 systemd logged `Service reached runtime time limit. Stopping.`, began stopping both dependents, and marked the guard `Result=timeout`. After 25 seconds, guard was failed/failed, MainPID=0; collector and materializer each inactive/dead, MainPID=0, Result=success. Operator removed the test unit files, daemon-reloaded, reset failed state, and verified all three LoadState=not-found and ActiveState=inactive.

**PASS limited to:** tcou dummy-unit guard runtime expiration dependency propagation. Alongside SIGKILL and normal stop, all three tcou dummy scenarios passed. Other hosts and real workloads remain untested.

## kah-01 dummy guard SIGKILL result — 2026-10-08 (host journal)

On kah-01, operator generated and verified the same three dummy units, checked all were initially absent, installed and started them. At 06:49:35 all three were active (guard PID 67597, collector 67601, materializer 67606). At 06:49:43 operator issued `systemctl kill --kill-whom=main --signal=SIGKILL` against the guard; journal confirmed status=9/KILL, Result=signal and systemd stopping both dependents. Three seconds later guard was failed/failed, MainPID=0, Result=signal; collector and materializer inactive/dead, MainPID=0, Result=success. Operator stopped units, removed all three test files and daemon-reloaded. Final LoadState=not-found for all; collector/materializer ActiveState=inactive; guard retained ActiveState=failed (normal failed-state retention pending targeted reset-failed). No live BF4PS service or database access was involved.

**PASS limited to:** kah-01 dummy-unit SIGKILL dependency propagation. Normal-stop and runtime-expiration tests remain pending on kah-01; hnl-01 remains untested.

## kah-01 dummy guard normal-stop result — 2026-10-08 (host journal)

After previous SIGKILL test, the guard's unloaded unit still showed ActiveState=failed, while collector and materializer were not-found/inactive. Operator installed previously generated dummy units, daemon-reloaded, and started all three successfully (guard PID 68287, collector PID 68290, materializer PID 68291). At 06:51:20 operator stopped only the guard via `systemctl stop bf4ps-stage9c-test-guard.service`. Journal shows systemd stopping both dependents at the same second, then the guard. All three finished ActiveState=inactive, SubState=dead, MainPID=0, Result=success. Operator stopped/removed the test units and daemon-reloaded; all three final LoadState=not-found and ActiveState=inactive.

**PASS limited to:** kah-01 dummy-unit normal-stop dependency propagation. kah-01 runtime expiration and all hnl-01 scenarios remain pending.

## kah-01 dummy guard runtime-expiration result — 2026-10-08 (host journal)

Operator confirmed all three units not-found/inactive, installed previously generated dummy units, and changed only installed guard `RuntimeMaxSec=90` to `RuntimeMaxSec=20`. `systemd-analyze verify` returned no errors. `systemctl show` confirmed guard RuntimeMaxUSec=20s, both dependents 1min 30s, and Restart=no for all three. At 06:53:59 all three started active (guard PID 69426, collector 69429, materializer 69430). At 06:54:19 journal logged guard runtime limit reached and systemd stopping both dependents; guard Result=timeout. After 25 seconds guard was failed/failed with MainPID=0; collector and materializer were inactive/dead, Result=success, MainPID=0. Operator stopped all three, removed dummy unit files, daemon-reloaded, targeted reset-failed for guard, and confirmed all three LoadState=not-found, ActiveState=inactive.

**PASS limited to:** kah-01 dummy-unit guard runtime expiration. All three kah-01 dummy dependency tests (SIGKILL, normal stop, runtime expiration) now pass; hnl-01 scenarios pending. No real BF4PS workload or database changes.

## hnl-01 dummy guard SIGKILL result — 2026-10-08 (host journal)

Operator generated the three dummy units locally, verified with `systemd-analyze verify` (no errors), confirmed all test units initially not-found/inactive, then installed and started all three. At 09:18:57 all three were active (guard PID 76199, collector 76202, materializer 76204). At 09:19:05 operator issued `systemctl kill --kill-whom=main --signal=SIGKILL` to the guard. Journal confirms guard main process killed with status=9/KILL, Result=signal, and systemd immediately stopped both dependents. Guard was failed/failed, MainPID=0; collector and materializer were inactive/dead, MainPID=0, Result=success. Operator stopped services, removed all dummy unit files, daemon-reloaded, reset only dummy guard failed state, and confirmed all three LoadState=not-found, ActiveState=inactive.

**PASS limited to:** hnl-01 dummy-unit SIGKILL dependency propagation. hnl-01 normal-stop and runtime-expiration scenarios pending. No real BF4PS workload or database changes.

## hnl-01 dummy guard normal-stop result — 2026-10-08 (host journal)

Operator confirmed all three test units initially not-found/inactive, installed and started dummy guard (PID 76867), collector (PID 76870), and materializer (PID 76871), all active/running. At 09:20:33, operator ran `systemctl stop bf4ps-stage9c-test-guard.service`; journal records systemd stopping both dependents at that same second and then stopping guard. All three reported inactive/dead, Result=success, MainPID=0. Operator removed all dummy unit files, daemon-reloaded, and verified all three LoadState=not-found and ActiveState=inactive.

**PASS limited to:** hnl-01 dummy-unit normal-stop dependency propagation. hnl-01 runtime expiration remains pending; no real BF4PS workload or database changes.

## hnl-01 dummy guard runtime-expiration result — 2026-10-08 (host journal)

Operator installed the three generated dummy units and changed only the installed guard to `RuntimeMaxSec=20`. `systemd-analyze verify` returned no errors; `systemctl show` confirmed guard RuntimeMaxUSec=20s, collector and materializer each 1min 30s, and Restart=no for all three. At 09:21:34 all three were active (guard PID 77377, collector 77380, materializer 77381). At 09:21:54 journal logged guard runtime limit reached, guard failed Result=timeout, and systemd stopping both dependents at the same second. Subsequent state: guard failed/failed, MainPID=0; collector and materializer inactive/dead, Result=success, MainPID=0. Operator stopped the dummy units, removed all three installed files, daemon-reloaded, reset the expected guard failure, and confirmed all three LoadState=not-found, ActiveState=inactive.

**PASS limited to:** hnl-01 dummy-unit runtime-expiration dependency propagation. The complete 3-host × 3-scenario dummy systemd validation matrix is now 9/9 PASS (tcou, kah-01, hnl-01; guard SIGKILL, normal stop, and runtime expiration). This does not prove real BF4PS supervision, lease enforcement, abort/drain atomicity, or six-hour readiness. No real BF4PS workload or database changes occurred.
