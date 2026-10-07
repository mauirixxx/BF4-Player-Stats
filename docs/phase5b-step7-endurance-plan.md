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
