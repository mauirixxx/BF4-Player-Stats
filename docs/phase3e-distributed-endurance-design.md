# BF4PS Phase 3E distributed endurance and physical-host recovery design

Status: **FROZEN implementation input**

Date: 2026-10-04 UTC

Parent design: `docs/phase3-distributed-collector-design.md`

Phase 3D evidence: `docs/phase3d-three-host-validation.md`

Current Alembic head at design freeze: `0003_request_gates`

## Objective

Phase 3E moves beyond Phase 3D's bounded 36-job correctness proof and validates that the distributed collector runtime remains correct during a longer, replenished workload while physical collectors deliberately leave and rejoin the system.

The central question is no longer whether three hosts can concurrently claim work. Phase 3D proved that. Phase 3E asks whether the same coordination model remains correct while the workload continues and collector availability changes.

Phase 3E is still a correctness/endurance experiment. It is **not** the Battlelog maximum-throughput or intentional throttle-boundary experiment.

## Frozen physical topology

Initial Phase 3E topology remains:

- `hnl-01`
- `kah-01`
- `tcou`

All collectors use the BF4PS test PostgreSQL primary through:

- `mak-db-02.bf4statusbot.com`
- database `bf4_playerstats_test`

Database configuration uses the FQDN. Cross-site runtime must not depend on short-name DNS resolution.

The three collectors retain separate stable collector identities. Stable identity must survive a process restart/rejoin.

## Egress identity rule

Collector identity, BF4PS request-gate identity, and actual public NAT/egress identity are separate concepts.

For this experiment each active BF4PS egress domain must have an explicitly configured `egress_key` matching the intended physical rate-limit domain. The runtime must never derive a request gate merely from collector UUID or hostname.

`tcou` currently shares public egress with BF4 Server Watcher host `mak-01`. Phase 3E preserves throttle evidence from that egress but does not intentionally increase BF4PS rate to provoke interaction with BF4SW.

## Workload model

Phase 3E uses:

- resource: `detailed`
- lane: `background`
- BF4PS test database only
- fresh/pristine soldiers selected explicitly before the live experiment
- all supported Phase 3 platforms represented throughout the cohort
- normal bounded feeder replenishment rather than pre-materializing the entire workload
- a hard global collection-attempt ceiling enforced independently of queue target depth

The live cohort and exact global ceiling are selected by a read-only preflight immediately before execution based on retained test data. They must be large enough to keep surviving collectors busy through the planned drain/stop/rejoin/reclamation sequence, but remain explicitly bounded.

The first Phase 3E live run should target **at least 120 attempts** if the test database contains enough pristine mixed-platform soldiers. A larger cohort may be frozen before implementation only if the same hard boundary and evidence requirements are preserved.

No unbounded bootstrap over the full discovered-player population is authorized by Phase 3E.

## Request pacing

Initial Phase 3E per-egress request pacing remains conservative. The starting interval is **5 seconds per BF4PS egress gate**, matching the conservative Phase 3D physical-host proof unless implementation evidence requires slower pacing.

Phase 3E does not automatically increase request rate in response to additional hosts or remaining backlog.

Every HTTP 403, HTTP 429, or classified Battlelog throttle result must be persisted/reported and included in final reconciliation. A throttle result is source evidence; it becomes a distributed-runtime failure only if the runtime mishandles ownership, bounds, pacing, retry state, or shutdown because of it.

## Feeder behavior

Unlike Phase 3D's fully armed frozen queue, Phase 3E exercises the normal bounded feeder path while multiple collectors are active.

The feeder must:

- materialize only work inside the frozen Phase 3E cohort;
- maintain bounded actionable queue depth rather than materializing the full cohort at once;
- never exceed the frozen global attempt ceiling;
- tolerate multiple collectors consuming the queue concurrently;
- stop producing new Phase 3E work when the global boundary is reached or the operator stop condition is asserted.

The exact feeder owner/coordination mechanism used by implementation must follow the existing Phase 3 design and database contracts; Phase 3E must not introduce an undocumented second scheduling authority.

## Required lifecycle sequence

The live validation is deliberately staged while useful work remains available.

### Stage A — sustained three-host operation

1. Start all three collectors under their stable identities.
2. Enable bounded feeder replenishment.
3. Allow enough repeated claim/finalize cycles to demonstrate continuing three-host work rather than a startup burst.
4. Confirm queue depth remains bounded and all three collectors continue making progress.

### Stage B — graceful drain

1. Select one remote collector for drain while it is participating in the workload.
2. Set its persistent operator `drained` control.
3. Verify it claims no new work after drain becomes effective.
4. Allow already-owned work to finalize gracefully.
5. Verify the two surviving collectors and feeder continue making progress.

### Stage C — restart while drained

1. Stop the drained collector cleanly.
2. Restart it under the same stable collector identity.
3. Verify persistent `drained` state survives restart.
4. Verify the restarted collector remains blocked from new claims.
5. Explicitly undrain it.
6. Verify it safely rejoins the active workload and resumes claim/finalize cycles.

### Stage D — abrupt owner loss and cross-host reclamation

1. Arrange one bounded test job to be owned by a selected collector using a deliberately short test lease suitable for deterministic validation.
2. Terminate/interrupt that collector without graceful release/finalization of that job.
3. Verify surviving collectors continue unrelated work.
4. Wait for the abandoned lease to expire.
5. Require a different physical collector to reclaim the same logical job.
6. Verify reclaim increments the attempt number and rotates the lease token.
7. Verify the stale former owner cannot mark running, renew, release, or finalize the reclaimed ownership if it returns.
8. Allow the current owner to finalize normally.

The deterministic short lease is a test-only control for this stage; it must not silently redefine normal production lease duration.

### Stage E — final convergence

1. Continue normal bounded collection until the frozen global ceiling or frozen cohort completion condition is reached.
2. Stop all collectors cleanly.
3. Stop feeder activity.
4. Run a read-only global reconciliation against jobs, events, collector state, request gates, and collection state.
5. Preserve evidence before any optional cleanup.

## Required PASS properties

Phase 3E passes only if global reconciliation demonstrates all of the following:

- no work outside the frozen Phase 3E cohort was attempted;
- the hard global attempt ceiling was never exceeded;
- multiple physical collectors repeatedly obtained and finalized work;
- queue replenishment remained bounded throughout the run;
- draining a collector prevented new claims without interrupting survivor progress;
- restart preserved stable collector identity and persistent operator drain state;
- explicit undrain safely returned the collector to service;
- abrupt owner loss did not stall unrelated work;
- an expired abandoned job was reclaimed by a different physical collector;
- reclamation incremented attempt number and rotated lease token;
- stale-owner mutations after reclamation were rejected;
- no duplicate simultaneous ownership/finalization occurred;
- collector/event identity snapshots remained attributable to the correct physical hosts;
- request gates remained consistent with configured BF4PS egress domains;
- all 403/429/throttle evidence was preserved and reconciled;
- final queue/job/event/state accounting is internally consistent;
- all collectors stop cleanly after the experiment;
- persistent operator controls are not silently overwritten.

A source-level Battlelog failure does not automatically fail Phase 3E if ownership, retry scheduling, event persistence, bounds, and shutdown remain correct. Distributed correctness and source success must be reported separately.

## Hard-stop conditions

Immediately stop new test work and preserve evidence if any of these occur:

- a soldier outside the frozen cohort is attempted;
- the global attempt ceiling is exceeded;
- duplicate simultaneous ownership is observed;
- a stale owner successfully mutates or finalizes reclaimed work;
- feeder activity escapes the frozen cohort/boundary;
- collector identity changes unexpectedly across restart;
- operator drain state is silently lost;
- request-gate identity does not match configured physical egress intent;
- unexplained queue/event/state accounting divergence occurs.

A 403/429 is not itself an instruction to blast through the limit. Preserve it, stop or back off according to the bounded harness/runtime policy, and reconcile the evidence before continuing any rate experiment.

## Explicit non-goals

Phase 3E does not:

- determine Battlelog's maximum safe request rate;
- intentionally trigger a Battlelog 403/429 block;
- run the full approximately 180k-player discovery population;
- deploy BF4PS collectors to the full BF4 Server Watcher eight-node fleet;
- coordinate BF4PS request gates with BF4SW request traffic;
- validate PostgreSQL primary failover during active BF4PS collection;
- change the production database schema unless implementation proves a schema change is required and that change is separately designed/documented first.

## Exit and next phase

Successful Phase 3E establishes that the distributed collector coordination model survives sustained bounded operation, graceful maintenance, restart/rejoin, abrupt owner loss, lease reclamation, and stale-owner fencing across physical hosts.

Only after Phase 3E evidence is documented should a separate controlled Battlelog operating-envelope experiment gradually increase bounded workload/rate while watching latency, HTTP 403/429, throttle classifications, and BF4PS/BF4SW shared-egress interaction.
