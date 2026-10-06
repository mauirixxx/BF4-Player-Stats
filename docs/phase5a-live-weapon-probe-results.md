# Phase 5A — Live Weapon Probe Results

Status: **LIVE WEAPON PATH VALIDATED**

## Scope

This checkpoint records the bounded live validation performed before the frozen Phase 5A 30-soldier cost-characterization cohort. The test database remained at Alembic revision `0003_request_gates` and the live probe used the established `phase3e-tcou` collector and PostgreSQL request gate.

## First live request — normalization failure

The first live weapon request targeted PC soldier `mauirixxx` (persona `236753552`). Battlelog returned a structurally usable weapon payload, but normalization rejected `mainWeaponStats[14].headshots` because the value was null.

The lifecycle behaved correctly: the attempt became `temporary_failure`, no weapon rows were persisted, the collection state recorded `battlelog_normalization`, and the job remained pending/unowned for retry. The worker did not crash.

A one-request, read-only payload inspector then measured the response at **553,329 bytes** with **174 `mainWeaponStats` entries**. Twenty Special/melee weapon entries legitimately supplied null values for `headshots`, `shotsFired`, `shotsHit`, and `timeEquipped`; `kills` remained numeric. Across the payload, non-null retained counters appeared as both integers and floats.

## Normalization correction

Commit `26e6366` changed null retained weapon counters to normalize as zero. Commit `90a7dfb` added regression coverage for the observed melee/null shape. The suite then passed **83 tests**.

This is a source-semantics correction, not a schema change: the existing retained weapon columns and current-state persistence contract remain unchanged.

## Second live request — success

After the null-counter correction, the bounded live probe selected the next pristine PC candidate:

- soldier ID: `3`
- persona ID: `1006267119911`
- name: `b33mooo`
- platform: `pc`
- queue job: `2210`

Observed result:

- Battlelog requests: **1**
- HTTP result: **200**
- measured response size: **568,544 bytes**
- normalized/persisted weapon rows: **174**
- collector duration: **1,405 ms**
- lifecycle result: **success**
- collection state: **success**
- consecutive failures: **0**
- completed queue job: **deleted**
- event metadata: `weapon_rows=174`, `response_bytes=568544`

The persisted row count exactly matched event metadata. This validates the live path from Battlelog fetch through normalization, atomic weapon persistence, collection-state convergence, event recording, and successful queue finalization.

## Cost evidence so far

The two directly measured PC weapon payloads were **553,329 bytes** and **568,544 bytes**, averaging **560,936.5 bytes** (~547.8 KiB) per weapon request. These are measured examples, not yet a population estimate.

The frozen Phase 5A experiment remains the authoritative next step for cost characterization: 30 soldiers total, exactly 10 PC / 10 PS4 / 10 Xbox One, with weapons and vehicles measured separately. The larger cohort will be used to characterize per-platform payload sizes, row amplification, request duration, PostgreSQL storage growth, and ultimately full-population capacity requirements.

## Acceptance

The bounded live weapon path is accepted for progression into the frozen Phase 5A cohort. Scaling beyond that frozen cohort remains gated on Phase 5A weapon + vehicle reconciliation and final cost characterization.