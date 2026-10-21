# Phase 5A weapon persistence integration

Status: **execution contract**

## Purpose

Before any live Battlelog weapon request is allowed to write production-shaped data, exercise the real PostgreSQL weapon persistence boundary against the writable BF4PS test database.

This step validates the transaction that already exists in `bf4ps/weapon_persistence.py`; it does not add a second persistence implementation.

## Safety boundary

The integration harness:

- targets only database `bf4_playerstats_test`;
- requires Alembic revision `0003_request_gates`;
- refuses a recovery/read-only server;
- performs **zero Battlelog requests**;
- creates a synthetic soldier and synthetic collector only inside one outer database transaction;
- executes all assertions against real PostgreSQL tables and constraints;
- rolls the entire outer transaction back at the end, including on success;
- therefore leaves **zero committed test rows**.

The harness must be run from the Phase 5A branch after the normal unit suite passes.

## Schema contract used

This harness is written against `docs/database-schema-reference.md` and the current Alembic migration chain through `0003_request_gates`.

Relevant invariants:

- `weapon_catalog.weapon_guid` is globally unique;
- `soldier_weapon_stats` is keyed by `(soldier_id, weapon_id)`;
- weapon collection state is the `weapons_*` column family on the one-row-per-soldier `collection_state` table;
- `collection_jobs` owns the resource/lane/lease tuple;
- successful persistence is fenced by `job_id + collector_uuid + lease_token + unexpired running lease`;
- `collection_events` is the durable attempt ledger.

If the schema reference and migrations ever disagree, this harness must not be modified by guessing; the disagreement must be reconciled first.

## Integration cases

### Case 1 — initial successful persistence

Create a synthetic PC soldier, enqueue and claim a real `weapons` background job, mark it running, then call `persist_weapon_success()` with two synthetic normalized weapons.

Verify:

- two catalog rows exist;
- two current soldier weapon rows exist with exact retained counters;
- `collection_state.weapons_state = 'success'`;
- weapon failure fields are cleared and failure count is zero;
- one `collection_success` event exists with the expected job/soldier/lease identity and metadata;
- the completed queue job is deleted.

### Case 2 — authoritative replacement

Enqueue a second real weapon job for the same synthetic soldier and persist a second payload where:

- one prior weapon remains with changed counters/metadata;
- one prior weapon disappears;
- one new weapon appears.

Verify:

- the soldier still has exactly two current weapon rows;
- the retained weapon contains the new counters;
- the disappeared weapon is absent from `soldier_weapon_stats`;
- the new weapon is present;
- the global catalog still retains all three GUIDs seen across both successful observations;
- the soldier has two weapon `collection_success` events;
- no weapon queue job remains.

This proves the endpoint is treated as authoritative for the soldier's current retained weapon set without incorrectly deleting global catalog history.

### Case 3 — stale-owner fencing

Create and start a third real weapon job, then temporarily replace its lease token in PostgreSQL while retaining the original `ClaimedJob` object. Call `persist_weapon_success()` using the stale token.

Expected result: `RuntimeError` with the lease-ownership rejection and **no weapon data mutation**. The lease-token mutation is isolated in a savepoint and rolled back after the assertion.

This proves stale workers cannot overwrite weapon state after losing ownership.

## Acceptance

The harness passes only if all three cases pass and the outer transaction is rolled back. A passing run authorizes the next Phase 5A step: connect the weapon collector orchestration path to the PostgreSQL request gate and perform a deliberately bounded first live Battlelog weapon collection.
