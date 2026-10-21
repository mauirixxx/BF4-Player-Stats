# Phase 2 mixed-platform runtime failure evidence

Date: 2026-10-04

Status: **preserved live evidence; do not rewrite as a clean 9/9 run**

## Purpose

Record the first frozen 3/3/3 PC / PS4 / Xbox One sustained-runtime execution exactly because it exposed a retry scheduling pathology that an all-success run would not have shown.

The target database was `bf4_playerstats_test`, writable primary, Alembic head `0003_request_gates`.

Frozen cohort:

- PC: soldier IDs 17, 18, 19
- Xbox One: soldier IDs 93, 94, 95
- PS4: soldier IDs 105, 106, 107
- target depth: 1
- hard attempt ceiling: 9
- retry delay: 300 seconds

## Observed result

The runtime reported:

```text
jobs attempted:    9
jobs succeeded:    8
jobs failed:       1
feeder passes:     4732
jobs materialized: 8
stopped by control:False
```

Final cohort state showed successful detailed collection for soldiers 17, 18, 19, 93, 94, 95, 105, and 106. Soldier 107 remained `never_attempted` with no detailed current row.

The important timing evidence was:

- soldier 17 success: `2026-10-04 06:03:41.001614+00:00`
- soldier 18 eventual success: `2026-10-04 06:08:43.438242+00:00`

That approximately five-minute gap matches the configured 300-second retry delay. After soldier 18 recovered, the remaining successful collections completed normally through soldier 106.

The harness then failed its assertion that exactly nine jobs must have been materialized:

```text
RuntimeError: expected 9 materialized jobs, got 8
```

## Diagnosis

The live evidence is consistent with one retryable failure consuming one process-level attempt while leaving the same queue row pending/recoverable with a future `eligible_at`.

The Phase 2 feeder at the time counted every pending/claimed/running detailed/background row as actionable depth. Therefore a pending retry job in its 300-second cooldown satisfied target depth 1 even though the collector could not claim it yet. The runtime repeatedly ran feeder passes while waiting for that retry to become eligible.

When the retry became eligible, soldier 18 recovered successfully. Because both the failed attempt and the recovery attempt counted toward the hard nine-attempt ceiling, the runtime reached that ceiling after soldier 106 and never attempted soldier 107.

A second issue was identified in the same feeder logic: when `allowed_soldier_ids` restricted materialization to a frozen validation cohort, actionable-depth counting was still global rather than scoped to that cohort.

## Required semantics

For the bounded Phase 2 feeder, **actionable working depth** means work capable of consuming a collector now:

- `claimed` jobs;
- `running` jobs; and
- `pending` jobs whose `eligible_at <= now()`.

A pending retry job whose eligibility is still in the future remains preserved in the queue but must not block materialization of another never-attempted soldier.

When `allowed_soldier_ids` is supplied, actionable-depth accounting must use the same cohort boundary as materialization. The existing `max_soldier_id` safety boundary must also apply to depth accounting.

## Preservation / recovery rule

Do **not** clean or reset the retained mixed-platform state merely to manufacture a fresh 9/9 result. The partial run is useful evidence.

After the feeder correction is validated, recovery should continue from the retained state and demonstrate that the remaining never-attempted cohort member can be collected without erasing the prior failure/recovery history.

## Harness lesson

`jobs_materialized == max_jobs` is not a valid general runtime invariant once retries exist. `max_jobs` is an attempt ceiling, while materialization counts newly created queue rows. One queue row may consume more than one attempt across retry/recovery.
