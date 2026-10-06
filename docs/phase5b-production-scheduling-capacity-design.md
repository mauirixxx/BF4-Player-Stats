# Phase 5B — Production Collection Scheduling and Capacity Design

Status: **DRAFT DESIGN — implementation not authorized**

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
