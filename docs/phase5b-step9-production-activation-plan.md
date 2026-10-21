# Phase 5B Step 9 — Bounded production activation plan

Status: **STAGE 9B ACCEPTED — Stage 9C preflight in progress; live Stage 9C not yet authorized**

Date: 2026-10-07 UTC

## Purpose

Step 9 converts the accepted Step 7/8 endurance evidence into a deliberately
bounded production activation. It is not an authorization for historical
backfill, faster request pacing, or immediate unattended full-scale operation.

The objective is to activate the already-frozen observation-driven scheduling
policy prospectively, prove that real BF4SW observations materialize only the
expected bounded work, and expand operating time only after read-only
checkpoints remain clean.

## Accepted evidence entering Step 9

Steps 7 and 8 are accepted.

The endurance run demonstrated:

- three distributed Phase 3E collectors;
- 3,888 physical attempts at the hard run ceiling;
- 3,888 matching terminal events;
- 3,864 unique jobs and 24 legitimate retry attempts;
- zero duplicate attempt or terminal identities;
- zero attempts without terminals and zero terminals without starts;
- exact rolling-one-hour maximum of 1,296 background starts;
- zero HTTP 403/429 or Battlelog throttle evidence;
- zero collection-persistence failures;
- zero foreign physical starts;
- first-retry timing no sooner than the frozen 15-minute policy;
- exact retry displacement of 24 pristine initial jobs;
- clean resource state and due-time reconciliation.

The existing five-second per-egress request gate and 1,296-attempt rolling-hour
background budget therefore remain unchanged.

## Hard rollout boundaries

Step 9 does not authorize:

- historical/full-population bootstrap;
- materializing jobs from BF4SW observations older than the production cutover;
- faster than five seconds per egress;
- more than 1,296 automatic background starts in any rolling hour;
- treating detailed/weapons/vehicles as an atomic bundle;
- changing the frozen active/recent/inactive freshness policy;
- adding collector egresses merely to increase capacity;
- enabling production without a timezone-aware materialization cutover;
- silently consuming Step 7 experimental residue as production work.

Production activation remains an operator action after implementation and
preflight pass.

## Step 7 residue boundary

The accepted endurance database intentionally retains 24 pristine pending
Step 7 weapon jobs. They exist because 24 retries consumed the shared 3,888
physical-attempt ceiling and displaced exactly 24 initial jobs.

Those rows are experimental residue, not production demand.

Before any unrestricted production collector is started, Step 9 must provide
an explicit, auditable cleanup operation that removes only the frozen Step 7
residual queue rows proven by the Step 8 reconciliation. Cleanup must refuse to
act if the residue no longer has the accepted shape.

The cleanup operation must not delete collection events or collection-state
evidence. The accepted Step 7/8 ledger remains historical evidence.

## Prospective materialization cutover

Production discovery/materialization must use an explicit timezone-aware
cutover timestamp chosen immediately before activation.

Observations older than the cutover continue to participate in normal identity
discovery/reconciliation but must not materialize production collection jobs.

This preserves the activation fence already implemented in the discovery
service and prevents historical catch-up from turning the existing BF4PS
population into bootstrap debt.

Only genuinely qualifying observations at or after the cutover may create
production work.

## Production collector service requirement

Step 7's endurance worker is a bounded validation harness and must not be
promoted implicitly into an unattended production daemon.

Before live activation, the repository must have an explicit production
collector entrypoint/service configuration that:

- registers the frozen collector identity and egress key;
- uses the normal durable collection queue;
- enables the production background admission policy;
- retains the five-second request gate;
- processes detailed, weapons, and vehicles independently;
- honors collector enabled/drained state;
- heartbeats and clears ownership normally;
- survives ordinary temporary failures without bypassing retry policy;
- shuts down cleanly on SIGINT/SIGTERM;
- does not contain Step 7 cohort allowlists or the Step 7 3,888-attempt ceiling;
- does not enable discovery/materialization by itself.

Service packaging and operator commands must be documented before activation.

## Pre-activation gate

A read-only Step 9 preflight must verify immediately before cleanup/activation:

- target database is exactly the intended BF4PS database;
- Alembic head is the documented current head;
- target is the writable primary;
- Step 7/8 accepted marker/evidence is present;
- the only known Step 7 residual queue work has the accepted pristine shape;
- no claimed/running Step 7 jobs remain;
- collector identities and egress keys match the frozen Phase 3E identities;
- collectors are not concurrently processing unexpected work;
- production materialization is not already active through another service;
- no unexpected background queue exists that would be consumed at startup.

The preflight performs zero Battlelog requests and zero database writes.

## Cleanup gate

After a successful read-only preflight, a dedicated cleanup command may remove
only the 24 accepted Step 7 pristine pending weapon jobs.

The cleanup must be transactional and fail closed unless every target row is:

- a member of the frozen Step 7 cohort;
- resource `weapons`;
- lane `background`;
- priority class `bootstrap`;
- reason `phase5b_step7_endurance`;
- status `pending`;
- attempt count zero;
- unowned and without lease/claim/start/error state;
- still paired with `weapons_state = 'never_attempted'`.

The command must require the exact accepted count of 24 before deleting
anything and must verify zero matching residue remains before commit.

No collection event or collection-state row is deleted or rewritten.

## Activation stages

### Stage 9A — implementation and dry validation

**COMPLETE / ACCEPTED — 2026-10-07.**

No production Battlelog traffic was used during Stage 9A.

Implement and validate:

1. read-only preflight;
2. exact Step 7 residue cleanup command;
3. production collector service/entrypoint;
4. read-only production health/audit command;
5. operator documentation for start, stop, drain, resume, and rollback;
6. automated tests and rollback-only database exercises where applicable.

Stage 9A completion authorizes a separate live decision; it does not itself
start production.

Accepted Stage 9A evidence includes:

- exact Step 7 residue cleanup with historical events/state preserved;
- post-cleanup forensic verification PASS;
- production collector daemon with stable frozen identities and production
  admission/request-gate contract;
- fail-closed drain/resume operator control;
- rollback-only live PostgreSQL control exercise PASS with zero persistent
  mutation;
- read-only final activation readiness PASS;
- cutover-aware read-only production checkpoint audit;
- full automated suite PASS at 283 tests;
- external process checks on tcou, hnl-01, and kah-01 all PASS;
- tcou's existing discovery process was observed without
  `--materialize-production-jobs`;
- hnl-01 and kah-01 had no BF4PS discovery/materialization process;
- zero Battlelog requests were introduced by the Stage 9A dry gates.

Stage 9B remains separately authorization-gated.

### Stage 9B — prospective canary

After explicit operator authorization:

1. run final read-only preflight;
2. perform exact Step 7 residue cleanup;
3. choose and record a timezone-aware materialization cutover immediately
   before activation;
4. enable production materialization prospectively;
5. start **one** frozen production collector/egress;
6. observe for one hour.

The one-egress canary deliberately limits physical capacity while validating
real production materialization and service packaging. The request gate remains
five seconds and the aggregate background scheduler remains capped at 1,296
per rolling hour; one egress cannot physically approach the three-egress raw
ceiling.

Acceptance requires:

- no historical bootstrap flood;
- no 403/429/throttle evidence;
- no persistence failures;
- no foreign/unexpected work;
- no ownership/lease anomalies;
- materialized jobs attributable to post-cutover observations;
- resource-specific due/freshness behavior remains correct;
- queue growth remains explainable and bounded;
- clean stop/restart behavior.

Any violation pauses rollout before additional collectors are enabled.

### Stage 9C — three-egress bounded production

If Stage 9B passes, start the remaining two frozen Phase 3E collectors.

Operate for an initial six-hour checkpoint with the same:

- five-second per-egress request gate;
- 1,296 rolling-hour aggregate background ceiling;
- frozen fairness policy;
- frozen retry policy;
- prospective cutover.

Read-only checkpoint audits must confirm physical/terminal accounting,
rolling-hour budget, throttling, persistence, retry debt, queue ownership,
materialization reasons/classes, and queue growth.

### Stage 9D — 24-hour soak

After a clean six-hour checkpoint, continue unchanged to a 24-hour production
soak.

No rate or policy expansion occurs merely because the six-hour checkpoint
passes.

The 24-hour audit becomes the first evidence for whether observed real
production demand fits the frozen 60-percent background budget and whether
queue growth is stable.

## Pause/abort policy

Immediately stop admitting new production collection traffic and preserve
evidence on:

- HTTP 403;
- HTTP 429;
- `battlelog_throttle`;
- collection persistence failure;
- physical/terminal accounting anomaly;
- rolling-hour background starts above 1,296;
- unexpected historical bootstrap materialization;
- unexpected foreign queue work consumed by production collectors;
- repeated ownership/lease corruption;
- database target/revision/primary mismatch.

An ordinary classified temporary Battlelog failure is not itself an abort
condition. It follows the frozen resource-specific retry policy.

When paused, do not delete diagnostic events or failure debt merely to obtain a
clean audit.

## Rollback model

The production switch is reversible operationally:

1. stop/drain production collectors;
2. stop production materialization so new BF4SW observations cannot create
   additional production jobs;
3. leave durable events and collection state intact;
4. inspect pending production queue work before deciding whether it should
   remain for a later restart or be removed by a separately designed,
   provenance-scoped cleanup.

Rollback must never mean deleting historical collection evidence.

## Expansion rule

Step 9 does not pre-authorize additional egresses, faster gates, broader
freshness rules, or historical bootstrap after a successful 24-hour soak.

Any such expansion requires new evidence and a separate design decision.

## Next implementation deliverable

The next authorized work is **Stage 9A only**:

- implement the read-only preflight;
- implement the exact Step 7 residue cleanup with fail-closed provenance
  checks;
- implement/package the production collector service;
- implement the read-only production checkpoint audit;
- add tests and operator documentation.

No new live Battlelog request is authorized by this design freeze.

## Stage 9B accepted production canary — 2026-10-08 UTC

**ACCEPTED.** One-hour tcou-only canary completed and both processes were stopped.
Frozen materialization cutover: `2026-10-08T00:47:34.757784+00:00`.
Frozen exclusive event boundary: `11558`. Neither may be regenerated for Stage 9C.

Final stopped read-only audit (repeated at Stage 9C preflight): 466 physical attempts,
466 matching terminal events, 464 successes, 2 classified temporary failures;
no duplicate/missing terminals, no 403/429/throttle or persistence events,
no foreign starts, no unexpected background provenance, no owned jobs.
Peak rolling-hour starts: 430 of the 1,296 ceiling.

Failure for Sundaro (PS4 weapons): HTTP 503, event 11982, recovered with
HTTP 200 on attempt 2 (event 12140), 15-minute retry policy observed;
weapons state success, failure count zero, job removed.
Failure for moonMindman (PS4 weapons): read timeout, event 12482,
classified `battlelog_transport`, 900-second retry, weapons state
`temporary_failure`, one pending job 6722 due at
`2026-10-08T02:20:03.422169+00:00`. Preserve this legitimate debt.

Stage 9C preflight evidence: tcou, hnl-01, kah-01 all on branch
`feature/phase5a-cost-cohort` at commit
`3ea3839cd7c37027fe69b48da6130b18be9a9fcc`, Python 3.12.3;
all had entrypoint and DB environment, no active collector/discovery processes.
All three connected to writable `bf4_playerstats_test` at revision
`0003_request_gates`; registry has the three expected stable identities,
all enabled/undrained, heartbeat unknown, no current ownership or running jobs.
Distinct public IPv4 egress observed: tcou 72.253.18.166,
hnl-01 76.81.69.106, kah-01 98.155.184.38, no proxy environment reported.
This proves independent public egress at check time, not Battlelog reachability.

**Stage 9C is NOT started.** Remaining gates: confirm deployment-specific
Battlelog connectivity without initiating collection; establish coordinated
fleet-wide stop on abort, restart materialization with the SAME frozen cutover,
and explicitly authorize six-hour collection. No queue reset or historical backfill.
