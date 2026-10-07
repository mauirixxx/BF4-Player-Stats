# Phase 5B Step 7 — Multi-hour production-scheduler endurance plan

Status: **FROZEN TEST ENVELOPE — broad production rollout remains unauthorized**

Date: 2026-10-07 UTC

## Purpose

Step 7 validates sustained distributed operation of the frozen Phase 5B production
scheduler after the successful Step 6 bounded live cohort. It is an endurance
test, not a Battlelog rate-limit search, payload-cost experiment, or broad
production rollout.

Step 6 established a clean baseline: 27 physical attempts, 27 terminal successes,
zero 403/429/throttle evidence, zero persistence failures, zero residual cohort
jobs, correct resource due intervals, and participation from all three frozen
Phase 3E collectors.

## Frozen live envelope

- Target database: `bf4_playerstats_test`
- Alembic revision: `0003_request_gates`
- Collectors/egresses: `phase3e-hnl-01`, `phase3e-kah-01`, `phase3e-tcou`
- Resources: `detailed`, `weapons`, `vehicles`
- Existing physical request gate: **5 seconds per egress**, unchanged
- Production background service admission: **enabled**
- Production rolling-hour background ceiling: **1,296 attempts**
- Endurance wall-clock ceiling: **3 hours**
- Endurance aggregate physical-attempt ceiling: **3,888**
- Initial cohort: **1,296 soldiers**
- Platform balance: **432 PC / 432 PS4 / 432 Xbox One**
- Initial jobs: **3,888** (three independent resource jobs per soldier)
- Initial priority class: **bootstrap**
- Initial cohort eligibility: all three retained resources must be
  `never_attempted` at seed time.
- Discovery/materializer: **disabled for this experiment**
- No historical/full-population bootstrap is authorized.

The 3,888 attempt ceiling is three times the frozen 1,296-attempt rolling-hour
service budget. It is an absolute safety ceiling, not an assertion that 3,888
requests must fit inside the three-hour wall-clock window. Because admission is
a rolling one-hour window, the scheduler may naturally alternate between
service bursts and periods waiting for prior attempts to age out. That behavior
is part of the endurance evidence.

Retries consume the same 3,888 aggregate physical-attempt budget. A retry does
not increase the ceiling. Ordinary temporary failures remain valid evidence and
use the frozen retry policy (15 minutes, 1 hour, 6 hours, then 24 hours).
Successful sibling resources are not re-fetched because another resource fails.

## Cohort selection

The seed operation selects exactly 432 soldiers per platform from the current
BF4PS population. A candidate must:

1. have a `collection_state` row;
2. have `detailed_state = 'never_attempted'`;
3. have `weapons_state = 'never_attempted'`;
4. have `vehicles_state = 'never_attempted'`;
5. have no existing `collection_jobs` row for any retained resource;
6. not belong to the completed Step 6 cohort.

Selection is deterministic within platform by `soldier_id`. The exact selected
soldier IDs are frozen into the Step 7 run-marker metadata so workers and the
post-run audit use the same allowlist after successful jobs disappear from the
queue.

## What Step 7 is testing

Step 7 tests:

- sustained distributed claiming across all three collectors;
- PostgreSQL request-gate pacing over hours;
- rolling-hour production admission and re-admission;
- queue ownership/lease stability;
- all three retained resources under sustained mixed demand;
- natural temporary-failure/retry behavior if Battlelog produces it;
- shared weapon/vehicle catalog persistence under sustained concurrency;
- exact durable physical-attempt accounting;
- no duplicate attempt identities;
- resource-specific success/failure state transitions;
- due times of +24 hours detailed and +7 days weapons/vehicles;
- clean collector heartbeat/stop behavior;
- absence of foreign Step 7 physical requests.

The existing rollback-only validation already proves the frozen 75/20/5
reservation mechanics. This live endurance cohort is intentionally legitimate
bootstrap work; it does not falsify production semantics by relabeling pristine
soldiers as active or retry work merely to manufacture a fairness mixture.
Natural failures, if any, may create real recovery work during the run.

## Abort conditions

All Step 7 workers must stop on the first observed:

- HTTP 403;
- HTTP 429;
- `battlelog_throttle` classification;
- `collection_persistence_failure`;
- foreign physical claim/request by a Step 7 collector;
- target database/revision/primary mismatch;
- cohort/allowlist mismatch;
- aggregate attempt-ceiling anomaly;
- wall-clock expiration.

A normal classified temporary failure is not by itself an abort condition unless
it is a throttle signal. It remains queued under the frozen retry policy.

## Acceptance and Step 8

Step 7 is operationally complete when all workers stop because the three-hour
window expires, the 3,888-attempt ceiling is reached, no eligible cohort work
remains, or an abort condition fires.

Step 8 performs the authoritative read-only reconciliation. It must examine at
least:

- distinct physical starts and terminal outcomes;
- attempts without terminals and terminals without starts;
- request counts by resource/platform/collector;
- rolling-hour admission behavior;
- per-egress request spacing;
- 403/429/throttle evidence;
- persistence failures;
- retries and retry spacing;
- residual queue state and ownership;
- collection-state success/failure debt;
- successful resource due intervals;
- foreign physical starts;
- collector registry state after shutdown.

Broad production materialization remains disabled until Step 7 and Step 8 are
accepted.


## Accepted Step 7/8 result — 2026-10-07 UTC

Status: **PASS — endurance and forensic reconciliation accepted**

Repository validation before the final forensic audit:

- repository head: `0c4eec13d51ef107da3b81a46a8beb07b41f37e5`;
- explicit Python compilation of the Step 8 audit and its test: PASS;
- full automated suite: **241 passed**.

The Step 7 run used run marker event 3781 and immutable live-start event 3782.
All three frozen Phase 3E collectors shared the same live start timestamp:
`2026-10-07T10:05:54.822805+00:00`.

The run reached the exact aggregate physical-attempt ceiling:

- physical attempts: **3,888 / 3,888**;
- unique jobs attempted: **3,864**;
- retry attempts: **24**;
- terminal events: **3,888**;
- terminal successes: **3,864**;
- terminal failures: **24**;
- duplicate attempt keys: **0**;
- duplicate terminal keys: **0**;
- attempts without terminal: **0**;
- terminals without start: **0**.

Collector participation was:

- `phase3e-hnl-01`: 1,160 physical attempts;
- `phase3e-kah-01`: 1,147 physical attempts;
- `phase3e-tcou`: 1,581 physical attempts.

The exact maximum number of durable physical starts in any rolling one-hour
window was **1,296**, equal to and not greater than the frozen production
background-service ceiling.

Natural temporary failures exercised the retry path. The minimum observed
retry gap was **901.592113 seconds**, satisfying the first frozen retry delay
of no sooner than 15 minutes. There was:

- zero HTTP 403/429 or `battlelog_throttle` evidence;
- zero collection-persistence failures;
- zero foreign physical starts by the Step 7 collectors.

Because retries consume the same hard 3,888-attempt budget, the 24 retries
displaced exactly 24 pristine initial jobs. The final queue therefore retained
24 pending, unowned, never-attempted weapon jobs. This is accepted ceiling
behavior, not unresolved attempt debt:

- remaining cohort jobs: **24**;
- pristine pending remaining: **24**;
- owned/non-pending remaining: **0**;
- unique jobs attempted + remaining initial jobs: **3,888**;
- retry displacement exact: **true**.

All 1,296 cohort soldiers retained collection-state rows. The final audit found
zero invalid state rows, zero successful-resource due-interval mismatches, and
zero unexplained pristine states.

### Request-gate timing interpretation

The forensic audit observed a minimum gap of 4.974251 seconds between adjacent
`collection_attempt_started` event timestamps on the same egress. There were
960 observed event gaps below 5.0 seconds, including 35 below 4.99 seconds.

These event timestamps are retained as diagnostic evidence but are not the
authoritative request-gate reservation clock. The PostgreSQL request gate
reserves the outbound slot before the worker waits; the durable
`collection_attempt_started` event is committed afterward in a separate
transaction immediately before HTTP. Transaction and scheduling displacement
can therefore make adjacent attempt-event timestamps differ slightly from the
reserved gate interval. The accepted hard pacing authority remains the
PostgreSQL request-gate reservation mechanism; the event-timestamp diagnostic
must not be interpreted as proof that the gate reserved slots faster than five
seconds.

### Acceptance boundary

Phase 5B validation Steps 7 and 8 are **accepted**. The endurance run directly
demonstrated the distributed scheduler reaching, but not exceeding, the frozen
1,296-attempt rolling-hour production background ceiling while preserving exact
physical-to-terminal accounting and clean persistence/throttle boundaries.

This acceptance does **not** itself enable production materialization, authorize
an unbounded historical bootstrap, or change the five-second per-egress gate.
Step 9 may now consider a deliberately bounded broader-production rollout under
a separately reviewed activation plan.
