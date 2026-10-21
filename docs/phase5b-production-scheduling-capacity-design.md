# Phase 5B — Production Collection Scheduling and Capacity Design

Status: **DESIGN FROZEN — scheduler implementation authorized; broad production rollout is not**

Date: 2026-10-06 UTC

Parent evidence: `docs/phase5a-full-stats-cost-characterization.md`

## Purpose

Phase 5B converts the accepted Phase 5A cost measurements into a production
scheduling policy. It does not increase Battlelog request rate and it does not
authorize bulk collection.

The design question is: how should BF4PS schedule `detailed`, `weapons`, and
`vehicles` independently so useful soldiers stay fresh, expensive resources
do not dominate the queue, retries remain bounded, and interactive work retains
priority?

## Frozen evidence entering Phase 5B

Phase 5A accepted a 30-soldier multiplatform cohort with:

- weapons: 30/30 success, 17,575,509 measured response bytes;
- vehicles: 30/30 success, 13,585,330 measured response bytes;
- combined weapons + vehicles: 31,160,839 bytes, 0.991 MiB per soldier;
- exactly two measured expensive-resource requests per completed soldier;
- production retained-stat shape: detailed + weapons + vehicles = three
  independent resource requests per soldier;
- zero 403/429/throttle evidence at the existing five-second per-egress gate;
- zero persistence failures and zero residual weapon/vehicle jobs.

Detailed collection was a successful cohort precondition. Phase 5A did not
measure detailed bytes and Phase 5B must not manufacture that measurement.

## Existing scheduling primitives to preserve

The current queue already defines:

1. `interactive`;
2. `active`;
3. `recent`;
4. `bootstrap`.

Claims order by priority class, then descending `priority_value`, then
`eligible_at`, `created_at`, and `job_id`.

Phase 5B should use this queue rather than introduce a second scheduling
authority. Resource due state belongs in the existing resource-prefixed
`collection_state` fields, including `<resource>_next_due_at`.

The PostgreSQL `request_gates` remain the physical outbound pacing authority.

## Capacity envelope

At the accepted five-second interval, one continuously busy egress has a
theoretical ceiling of:

- 12 requests/minute;
- 720 requests/hour;
- 17,280 requests/day.

Three independent egresses therefore have a theoretical aggregate ceiling of:

- 36 requests/minute;
- 2,160 requests/hour;
- 51,840 requests/day.

A complete retained-stat refresh of one soldier is structurally three requests
when detailed, weapons, and vehicles are all due. If every request slot were
used only for those three resources, the mathematical ceiling would be 17,280
complete soldier refreshes/day across three egresses.

That number is explicitly **not** a production target. Real capacity must
reserve headroom for retries, interactive work, maintenance/recovery,
temporarily slow responses, shared public egress with BF4 Server Watcher where
applicable, and future resource types.

## Scheduling model

The scheduler should classify soldier freshness demand independently from
resource cost.

### Soldier activity classes

The production policy should support at least:

- **active** — soldier has sufficiently recent external/source activity to
  justify highest background freshness;
- **recent** — soldier was active recently but is not currently in the active
  window;
- **bootstrap/inactive** — discovered soldier without recent activity evidence,
  or initial backlog work.

Exact activity-window durations are intentionally not frozen yet. They must be
chosen from live population/activity census evidence rather than guessed.

### Resource cadence

Each resource receives its own cadence by activity class. In particular,
weapons and vehicles must not automatically inherit the detailed cadence merely
because all three belong to the same soldier.

The intended shape is:

| Activity class | detailed | weapons | vehicles |
|---|---|---|---|
| active | fastest background cadence | slower | slower |
| recent | slower than active | substantially slower | substantially slower |
| bootstrap/inactive | sparse/on-demand | sparse/on-demand | sparse/on-demand |

The exact intervals remain **TBD pending census/capacity calculation**.

### No bundle requirement

A scheduler pass must not create a mandatory three-job bundle whenever one
resource becomes due. If detailed is due and weapons/vehicles are still fresh,
only detailed should become actionable.

This prevents the measured ~0.991 MiB weapon+vehicle cost from being paid
unnecessarily on every detailed refresh.

## Headroom policy

Production must not be designed to consume the 51,840-request/day theoretical
ceiling. Phase 5B must explicitly choose a normal background utilization budget
below 100 percent.

Before freezing a percentage, a read-only census must quantify:

- total soldiers by platform;
- soldiers with source activity in candidate active/recent windows;
- current resource-state distribution;
- age distribution of last successes;
- current pending/actionable jobs;
- retry/failure population;
- expected daily requests under candidate cadences.

The chosen schedule must fit inside the background budget with room for
interactive traffic and retry bursts.

## Fairness and starvation

Priority must preserve interactive responsiveness while preventing permanent
starvation of lower classes.

The existing queue's class ordering is useful but strict priority alone can
starve `recent` or `bootstrap` work under continuous active load. Phase 5B
must therefore define a bounded fairness mechanism before production rollout.
Possible implementation shapes include reserved background capacity,
age-based priority escalation, or weighted scheduling. The choice is deferred
until census data shows the expected class sizes.

Fairness must not bypass `eligible_at`, retry cooldowns, lease ownership, or
the request gate.

## Retry budget

Retry work consumes the same physical Battlelog capacity as first attempts and
must be included in capacity calculations.

A temporary failure must not cause successful sibling resources for the same
soldier to be re-fetched. Retry remains resource-specific. Existing lifecycle
state, cooldown, durable attempt accounting, and stale-owner fencing remain
authoritative.

Repeated source failures should receive progressive backoff or another bounded
retry policy before unrestricted production scheduling is enabled.

## Shared-egress caution

The BF4PS egress key is a BF4PS coordination domain, not proof that no other
application shares the public NAT address. In particular, tcou has previously
shared public egress with BF4 Server Watcher traffic.

Phase 5A proved the BF4PS workload was clean at the tested pacing; it did not
prove a combined BF4PS + BF4SW maximum safe rate. Phase 5B therefore keeps the
five-second BF4PS gate and treats cross-application egress pressure as a
separate operating-envelope concern.

## Required read-only census

Before choosing production intervals, build a zero-write/zero-request census
that reports enough information to model candidate schedules:

- total soldiers and platform split;
- counts by detailed/weapons/vehicles collection state;
- last-success age buckets for each resource;
- counts of soldiers seen/source-active in candidate time windows;
- queue counts by resource, priority class, status, and actionable/cooldown;
- failure/retry counts by resource and error class;
- current collector and egress inventory;
- request-gate inventory;
- historical request/event rates where durable evidence supports them.

The census should output data, not choose policy.

## Capacity calculator

After the census, build an offline/read-only calculator that accepts candidate
activity windows and resource cadences and reports:

- expected requests/day by activity class and resource;
- aggregate requests/day;
- percentage of theoretical three-egress capacity;
- reserved headroom;
- expected weapon+vehicle response bytes/day using **measured Phase 5A means**;
- retry sensitivity scenarios;
- whether lower-priority classes receive capacity under the proposed fairness
  policy.

Detailed bandwidth must remain labeled unknown/measured-separately until a
durable detailed byte measurement is available.

## Validation sequence

Implementation should proceed only after policy is frozen:

1. read-only population/activity census;
2. evaluate candidate schedules offline;
3. freeze activity windows, resource cadences, headroom, and fairness policy;
4. implement scheduler/materializer using existing queue/state primitives;
5. unit/integration test due-time and priority behavior;
6. bounded live cohort;
7. multi-hour endurance run with all three resources;
8. reconcile physical attempts, terminal events, queue/state, throttling, and
   achieved freshness;
9. only then consider broader production rollout.

## Hard boundaries

Phase 5B does not authorize:

- faster than five seconds per egress;
- unbounded full-population bootstrap;
- identical cadence for all resources without evidence;
- treating three resources as an atomic refresh bundle;
- a second queue/scheduling authority;
- deleting or rewriting accepted Phase 5A evidence;
- assuming catalog cardinality equals Phase 5A catalog growth;
- adding reconnaissance detailed bytes to measured traffic.

## First implementation deliverable

The next code deliverable is the **read-only production-scheduling census**.
It must make zero database writes and zero Battlelog requests. Its output will
be used to select candidate activity windows and cadences before scheduler code
is written.


## Read-only census evidence — 2026-10-06

The Phase 5B scheduling census completed against `bf4_playerstats_test` at
Alembic head `0003_request_gates`. It performed zero database writes and zero
Battlelog requests.

Population:

- total soldiers: 188,364;
- PC: 122,127;
- PS4: 31,565;
- Xbox One: 34,672;
- all 188,364 currently have a `bf4sw` soldier-source row.

Latest source-observation recency (this is discovery/source observation and is
**not** asserted to be gameplay activity):

- <1 hour: 3,939;
- 1-6 hours: 7,844;
- 6-24 hours: 13,114;
- 1-7 days: 47,936;
- 7-30 days: 80,558;
- >=30 days: 34,973.

Cumulative source-observed populations are therefore 3,939 within one hour,
11,783 within six hours, 24,897 within 24 hours, 72,833 within seven days, and
153,391 within 30 days.

Collection state at census time:

- detailed: 2,185 success, 1 temporary failure, 186,178 never attempted;
- profile: 188,364 never attempted;
- weapons: 41 success, 1 temporary failure, 188,322 never attempted;
- vehicles: 30 success, 188,334 never attempted.

The only current failure debt was one detailed normalization failure and one
weapon normalization failure, each with one consecutive failure. The queue was
empty.

The collector registry still contains historical Phase 2/3 experimental
collector identities and request gates in addition to the three Phase 3E
identities. Those historical rows must not be mistaken for currently intended
production capacity. The accepted capacity baseline remains the three Phase 3E
egress domains unless a later design explicitly changes it.

Durable request-history interpretation requires a chronology caveat. The
census showed 1,442 detailed terminal events in the preceding 24 hours but zero
detailed `collection_attempt_started` events. Durable pre-request markers were
introduced later during Phase 5A hardening, so older detailed terminal history
cannot be treated as exact physical-request accounting. Weapon/vehicle Phase 5A
runs do have the hardened attempt-start evidence.

### Immediate scale implication

At three egresses and a five-second gate, the absolute theoretical aggregate
capacity is 51,840 request slots/day. A one-time three-resource pass across all
188,364 discovered soldiers would require 565,092 physical requests, or about
10.9 days at that impossible-to-sustain 100-percent ceiling before retries,
interactive traffic, safety headroom, or other workloads.

Using the accepted Phase 5A weapon+vehicle mean of 1,038,694.6 bytes per
soldier, one weapons+vehicles pass across all 188,364 soldiers would transfer
approximately 182.2 GiB of measured response payload. Detailed traffic is not
included in that byte figure.

The census therefore supports tiered scheduling rather than uniform freshness
across the entire discovered population. Exact tier boundaries and cadences
remain unfrozen until the offline capacity calculator is evaluated.


## First capacity-model result — fixed recency tiers rejected

The first offline capacity calculation evaluated three intentionally contrasting
fixed-recency schedules against the accepted three-egress, five-second-gate
ceiling of 51,840 requests/day.

Results:

| Candidate | Requests/day | Theoretical utilization | Measured weapon+vehicle payload/day |
|---|---:|---:|---:|
| conservative hot set | 329,932.4 | 636.4% | 42.14 GiB |
| balanced hot set | 463,537.8 | 894.2% | 86.49 GiB |
| aggressive hot set | 821,164.4 | 1,584.0% | 129.73 GiB |

All three candidates are rejected. Even the conservative model exceeds the
absolute physical request ceiling by approximately 6.36x before retries,
interactive work, shared-egress pressure, or safety headroom.

This result changes the scheduling design direction. Static source-recency
buckets are useful for describing the population, but repeatedly refreshing
every member of a bucket at a fixed cadence is not a viable production
scheduler for the observed BF4PS population.

### Revised direction: event-driven working set

BF4SW source observations should be treated as scheduling signals that can
promote/touch a soldier's work rather than as membership in a permanently
re-polled fixed bucket. Inactivity should naturally reduce background demand.

The next model must therefore work from a **request budget first**:

1. reserve explicit capacity/headroom;
2. allocate a bounded budget among detailed, weapons, vehicles, retries, and
   interactive work;
3. use new/recent BF4SW observations to make soldiers eligible for those
   budgets;
4. coalesce repeated observations while a resource remains fresh;
5. allow inactivity to stop generating recurring expensive work;
6. preserve resource-specific due times and retries.

No production cadence is frozen by the rejected models.


## BF4SW source arrival/churn evidence — 2026-10-06

The read-only source-arrival/churn probe completed against
`bf4_playerstats_test` with zero database writes and zero Battlelog requests.

The current schema retains `soldier_sources.first_seen_at` and the latest
`soldier_sources.last_seen_at`; it does not retain every BF4SW observation.
Consequently:

- new-soldier arrival timing is directly measurable;
- current latest-touch recency is directly measurable;
- first-to-last observed lifetime is directly measurable;
- historical touch-event volume is **not derivable** from current BF4PS state.

At the measurement point there were 188,373 BF4SW-sourced soldiers.

### 24-hour working-set evidence

During the preceding 24 hours:

- 2,430 soldiers were newly discovered;
- 24,864 soldiers had their latest retained BF4SW observation in the window;
- 22,434 of those were returning identities first seen before the window;
- 2,400 of the 2,430 new arrivals had already been observed again.

Thus approximately 98.8 percent of the newly discovered 24-hour cohort had
already received a later source observation. The observed hot population is
therefore dominated by returning identities rather than one-shot discoveries.

### Seven-day evidence

During the corresponding seven-day windows:

- 19,955 soldiers were newly discovered;
- 72,817 soldiers had their latest retained BF4SW observation in the window;
- 52,862 were returning identities first seen before the window.

### Observed source-lifetime shape

Across all 188,373 BF4SW source rows:

- exact same first/last timestamp: 2,219 (about 1.18%);
- greater than zero but under one hour: 48,811;
- one hour to under one day: 22,684;
- one day to under seven days: 31,442;
- seven to under 30 days: 50,545;
- at least 30 days: 32,672.

These spans prove repeated/extended observation timing, not the number of
individual observations.

### Capacity implication

The arrival rate is materially smaller than the current recently observed
population. At the measured 24-hour arrival count, collecting all three
retained-stat resources exactly once for every newly discovered soldier would
require 7,290 requests/day, about 14.1 percent of the three-egress theoretical
51,840-request/day ceiling before retries.

By contrast, refreshing all three resources once for every soldier whose
latest source observation lies within 24 hours would require 74,592
requests/day, already about 143.9 percent of the theoretical ceiling.

Therefore Phase 5B should distinguish **arrival/bootstrap work** from
**returning refresh work**. A source observation should not imply that all
three resources must be fetched. Returning observations should primarily act
as eligibility/freshness signals, with each resource independently coalesced
against its last success / next-due state.

The current database cannot reconstruct the number of source touch events that
would have been presented to an online scheduler. If exact event-arrival rate
or coalescing efficiency is required before production rollout, it must be
measured prospectively rather than inferred from `last_seen_at`.


## Frozen Phase 5B production scheduling policy

The census, rejected fixed-tier models, and BF4SW source churn analysis provide
enough evidence to freeze the first production scheduling policy. This policy
replaces the earlier TBD cadence language where the two conflict.

### Scheduling signal and activity windows

BF4SW source observation is an **eligibility signal**, not an unconditional
request instruction.

For scheduling classification:

- **active**: latest BF4SW source observation is within 24 hours;
- **recent**: latest BF4SW source observation is older than 24 hours but within
  seven days;
- **inactive**: latest BF4SW source observation is older than seven days.

These classifications describe source observation, not proven gameplay
activity.

### New-soldier bootstrap

A newly discovered BF4SW soldier is eligible for one initial collection of
each retained-stat resource:

- detailed;
- weapons;
- vehicles.

These are three independent resource jobs, not an atomic bundle. Failure or
delay of one resource must not invalidate or re-fetch successful siblings.

Bootstrap is bounded by normal background scheduling capacity. Discovery must
never bypass the queue or request gate merely to complete initial collection.

### Returning-soldier freshness

A subsequent BF4SW observation may make stale resources eligible according to
their independent freshness:

| Source class | detailed | weapons | vehicles |
|---|---|---|---|
| active (<=24h) | 24 hours | 7 days | 7 days |
| recent (>24h to <=7d) | no observation-triggered refresh unless already due from an active period | no observation-triggered refresh unless already due | no observation-triggered refresh unless already due |
| inactive (>7d) | no recurring background refresh | no recurring background refresh | no recurring background refresh |

An observation received while a resource remains fresh produces no new
Battlelog request for that resource.

The scheduler must use the existing per-resource collection-state/due-time
fields. It must not infer sibling-resource freshness and must not create a
mandatory three-resource refresh bundle.

The conservative treatment of the recent class is intentional for the initial
production policy: recent/inactive identities remain known and queryable, but
source observation alone does not continuously create background refresh debt.
A later evidence-backed policy may broaden recent-class refresh behavior.

### Background capacity and headroom

The five-second per-egress request gate remains unchanged.

Normal automatically generated background work is budgeted to **no more than
60 percent of the three-egress theoretical capacity**, equivalent to:

- 31,104 request slots/day;
- 1,296 request slots/hour aggregate.

This is an admission/service budget, not a faster request rate. The remaining
40 percent is headroom for interactive work, retries, recovery/maintenance,
traffic variation, and shared-egress uncertainty.

If eligible background demand exceeds the budget, work waits; the scheduler
does not increase request rate or relax freshness rules to catch up.

### Priority and fairness

The existing priority classes remain authoritative:

1. interactive;
2. active;
3. recent;
4. bootstrap.

Interactive work retains strict precedence over background work.

Within automatic background service, starvation is bounded by reserving the
60-percent background budget as follows:

- up to 75 percent of background service for active work;
- at least 20 percent available to bootstrap work when bootstrap work is
  pending;
- at least 5 percent available to retry/recovery or otherwise eligible
  lower-priority background work when such work is pending.

Unused reserved capacity may be borrowed by other eligible background classes;
the reservation is a starvation floor when competing work exists, not a reason
to leave request slots idle.

Implementation may express these shares with service counters/token buckets or
an equivalent single-authority mechanism, but must continue to materialize and
claim work through the existing collection queue.

### Retry policy

Retries remain resource-specific.

For the initial production scheduler:

- first temporary failure: retry no sooner than 15 minutes;
- second consecutive temporary failure: retry no sooner than 1 hour;
- third: retry no sooner than 6 hours;
- fourth and later: retry no sooner than 24 hours;
- a successful collection resets that resource's consecutive-failure backoff.

An unavailable resource does not enter the temporary-failure retry loop.
Interactive/manual behavior for unavailable resources remains a separate
policy concern.

Retry work counts against background service capacity unless the originating
job is explicitly interactive.

### Explicit non-goals of this freeze

This freeze does not:

- authorize faster than five seconds per egress;
- authorize an unbounded historical bootstrap of all discovered soldiers;
- authorize broad production rollout before the validation sequence;
- define PostgreSQL storage sizing or retention-growth policy;
- treat Battlelog response bytes as database storage growth;
- add a second scheduling authority;
- claim source observation is proof of gameplay activity.

### Implementation authorization

Phase 5B validation steps 1 through 3 are complete. Scheduler/materializer
implementation under step 4 is now authorized on the feature branch.

Broad production collection remains unauthorized until implementation tests,
bounded live validation, multi-resource endurance, and reconciliation complete
the remaining validation sequence.


## Step 4 implementation validation — rollback-only database exercise

The first scheduler/materializer implementation slice passed the full automated
test suite (169 tests) and a rollback-only live PostgreSQL exercise against
`bf4_playerstats_test`, soldier 15 / PC persona 513446234 (`jdisa35w`).

The database exercise verified:

- a newly discovered soldier materializes detailed, weapons, and vehicles
  bootstrap jobs exactly once;
- replaying the same bootstrap observation is idempotent;
- an active returning soldier materializes only independently due resources;
- a recent (>24h) source observation creates no new refresh debt;
- no Battlelog requests are made by the validation harness;
- the validation transaction is rolled back, leaving zero committed database
  writes.

This validates the core Phase 5B eligibility/materialization mechanics before
they are connected to the BF4SW discovery ingestion path. Broad production
collection remains unauthorized.


## Step 4 implementation validation — background service and activation fence

Phase 5B Step 4 scheduler implementation completed its rollback-only
background-service database exercise against `bf4_playerstats_test` at Alembic
head `0003_request_gates`.

The code suite passed 198 tests before the database exercise. The rollback-only
exercise then proved against real PostgreSQL:

- eligible interactive work prevents new background admission;
- bootstrap receives its frozen starvation floor while pending;
- retry/recovery work receives its frozen starvation floor while pending;
- unused reservations are borrowable;
- the aggregate rolling-hour background ceiling is 1,296 attempts;
- zero Battlelog requests were issued;
- zero harness writes were committed.

The first database exercise attempt failed before policy validation because
PostgreSQL could not infer bound-parameter types inside the harness's synthetic
`jsonb_build_object` fixture. The fixture was corrected with explicit
PostgreSQL casts and the successful exercise was rerun. This was a harness
typing defect, not scheduler-policy evidence, and is retained as negative test
history.

A final activation review also found that the discovery service originally
propagated the opt-in materialization flag during startup cycles but omitted it
from recurring cycles. That wiring defect is fixed and regression-tested.

Production materialization remains disabled by default. Enabling it now also
requires an explicit timezone-aware materialization cutover timestamp.
BF4SW observations older than that cutover are imported/reconciled normally
but cannot materialize production jobs. This prevents historical catch-up after
a rebuild or delayed deployment from turning the known historical population
into an unbounded bootstrap queue merely because the materialization switch is
enabled.

The cutover is an activation fence, not authorization for broad rollout.
Bounded live-cohort validation remains required before production enablement.


## Step 4 status — implementation complete

Phase 5B Step 4 is **IMPLEMENTATION COMPLETE**.

Final implementation gate:

- repository head under test: `796decf6aef814a88d6619d29182de6a4d6aa37e`;
- Python compilation gate: PASS;
- full automated suite: **201 passed**;
- production materialization remains opt-in and disabled by default;
- activation requires an explicit timezone-aware cutover timestamp;
- broad production rollout remains unauthorized;
- no live Battlelog collection was authorized by completing this step.

Step 5 may now evaluate the implemented due-time, priority, retry, budget,
fairness, and activation behavior as an integrated scheduler. Step 6 bounded
live-cohort collection remains a separate later authorization boundary.


## Step 5 status — integrated scheduler validation complete

Phase 5B Step 5 is **COMPLETE**.

Final automated gate:

- repository head under test:
  `341cc8965147813b624d9f5744cbbfd5b120028a`;
- full automated suite: **205 passed**;
- no live Battlelog request was issued by the Step 5 validation.

The first Step 5 suite run produced 204 passes and one harness-safety-test
failure. The failing assertion prohibited the substring `requests.` anywhere
in the harness source and therefore matched the English docstring sentence
`Battlelog requests.`. It did not identify a network call. The guard was
corrected to reject actual Requests/httpx import forms while retaining the
explicit prohibition on the Battlelog fetch function. The corrected suite
passed 205/205. This negative result is retained because the validation guard
itself was what failed, not scheduler behavior.

A rollback-only integrated PostgreSQL exercise then completed against
`bf4_playerstats_test`, Alembic head `0003_request_gates`, using explicit
existing soldier 15 / PC persona 513446234 (`jdisa35w`).

The integrated lifecycle proved:

- new bootstrap materializes detailed, weapons, and vehicles exactly once;
- active returning observations materialize only independently due resources;
- recent observations create no new refresh debt;
- an independently due detailed resource enters the existing queue as active
  refresh work;
- production background admission claims that existing queue work and preserves
  normal lease ownership;
- first temporary detailed failure creates a 15-minute resource-specific retry;
- a new BF4SW observation during retry cooldown creates no duplicate or
  reclassified job;
- the retry reuses the same queue row and becomes attempt number two;
- successful retry clears detailed failure debt and sets detailed freshness
  due 24 hours after success;
- weapons and vehicles collection state remain unchanged throughout the
  detailed failure/retry/success lifecycle;
- the exercise issued zero Battlelog requests;
- the transaction was rolled back, leaving zero committed harness writes.

Together with the existing unit and rollback-only database evidence, Step 5
covers the frozen source-class boundaries, independent resource due times,
queue idempotence, retry progression, success reset, strict interactive
precedence, background fairness reservations, the 1,296-attempt rolling-hour
background ceiling, durable attempt accounting, and the activation cutover
fence.

No additional Step 5 test is required by current evidence.

### Authorization boundary after Step 5

Completion of Step 5 does **not** authorize broad production scheduling or
historical bootstrap.

Validation sequence step 6, the bounded live cohort, is now eligible for
explicit authorization. Step 6 is the first Phase 5B validation step that may
intentionally issue live Battlelog requests. It must retain explicit cohort
bounds, the existing five-second per-egress request gate, durable physical
attempt accounting, and post-run reconciliation before any endurance or
broader rollout decision.
