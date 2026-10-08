# Phase 5B Step 9 — Production operator runbook

Status: **STAGE 9A DRY OPERATIONS ONLY — live Stage 9B activation is not authorized**

This runbook operationalizes the frozen Step 9 design. It deliberately keeps
three controls separate:

1. **materialization** decides whether qualifying BF4SW observations may create
   production jobs;
2. **collector controls** decide whether a registered collector may claim work;
3. **process lifecycle** decides whether the collector daemon is running.

Starting a collector must never enable materialization implicitly.

## Current accepted checkpoint

The accepted Stage 9A database state after Step 7 residue cleanup is:

- database `bf4_playerstats_test`;
- Alembic revision `0003_request_gates`;
- Step 7 marker event ID 3781;
- Step 7 live-start event ID 3782;
- 3,888 physical attempts and 3,888 terminal events preserved;
- 3,864 unique jobs plus 24 retries preserved;
- zero Step 7 queue residue;
- zero background jobs;
- zero production collector ownership;
- 24 displaced weapon states still pristine `never_attempted`.

Re-run the read-only post-cleanup verifier before any later activation work:

```bash
cd /opt/bf4-player-stats
.venv/bin/python scripts/phase5b_step9_postcleanup_verify.py
```

Do **not** rerun `phase5b_step9_activation_preflight.py` after cleanup. That
pre-cleanup gate intentionally expects the 24 accepted Step 7 residue rows and
must fail once cleanup has succeeded.

## Production collector identities

Only these short hostnames are accepted by the production daemon:

- `hnl-01`
- `kah-01`
- `tcou`

The UUID, collector name, and egress key are frozen in
`bf4ps/production_hosts.py`. The daemon refuses an unknown hostname rather
than inventing an identity.

## Process lifecycle

The production entrypoint is:

```bash
cd /opt/bf4-player-stats
.venv/bin/python scripts/bf4ps_production_collector.py
```

**Do not run that command during Stage 9A.** It is documented here for the
separately authorized Stage 9B canary.

The process requires `BF4PS_DATABASE_URL`. It registers/heartbeats the stable
collector identity, honors `enabled` and `drained`, and exits cleanly on
SIGINT/SIGTERM. It does not enable discovery or production materialization.

For Stage 9B, start only the explicitly selected one-egress canary. Do not
start all three collectors together.

A normal process stop is SIGTERM (or Ctrl-C when foregrounded). The daemon's
clean-stop path marks heartbeat state unknown and clears `current_job_id`.
Stopping the process does not change operator-owned `enabled` or `drained`.

## Drain and resume semantics

`collectors.drained` is the operator-owned claim-control switch.

- `drained=true`: daemon remains alive and heartbeating but does not claim new
  jobs.
- `drained=false`: an enabled daemon may claim work normally.

Drain is preferred before a planned stop when the operator wants a quiet
boundary. Do not edit job ownership/lease columns manually.

The accepted operator control is:

```bash
.venv/bin/python scripts/bf4ps_production_collector_control.py drain --execute
.venv/bin/python scripts/bf4ps_production_collector_control.py resume --execute
```

It fails closed on the database/revision/primary and frozen collector identity
before changing `collectors.drained`. Do not replace it with ad-hoc ownership
or queue SQL.

## Disable versus drain

`enabled=false` means the daemon exits cleanly when it next observes control
state. It is a stronger administrative control than drain.

Use drain for a temporary no-new-claims state. Use disable when the collector
must not continue running. Re-enabling does not start a stopped OS process; it
only permits the process to run when subsequently started.

## Materialization activation

Materialization is controlled by the discovery service, not by the collector
daemon.

For Stage 9B, a timezone-aware cutover must be chosen immediately before
activation. The discovery service must be started/configured with production
materialization enabled and that explicit cutover. Observations older than the
cutover must not create production collection jobs.

Before doing this, verify at the deployment/process level that no other
discovery service is already running with production materialization enabled.
The current database schema does not durably record the discovery CLI flags,
so a database-only preflight cannot prove this fact.

Do not reuse an old cutover timestamp merely for convenience.

## Stage 9B canary order

Stage 9B requires separate explicit operator authorization. Once authorized,
the order is:

1. verify code revision and test gate;
2. run the read-only post-cleanup/final readiness checks;
3. verify no other materializing discovery process is active;
4. choose and record a new timezone-aware cutover;
5. record the audit/event boundary used for the production checkpoint;
6. enable prospective production materialization with that cutover;
7. start exactly one production collector/egress;
8. observe for one hour;
9. run `phase5b_step9_checkpoint_audit.py --cutover-at <CUTOVER> --since-event-id <BOUNDARY>`;
10. stop/pause before expansion if any abort condition appears.

The one-hour canary does not authorize the other two collectors automatically.

## Read-only checkpoint audit

After an authorized live boundary exists:

```bash
cd /opt/bf4-player-stats
.venv/bin/python scripts/phase5b_step9_checkpoint_audit.py \
  --cutover-at <CUTOVER> \
  --since-event-id <BOUNDARY>
```

The audit performs no Battlelog requests and no database writes. Preserve its
complete output with the activation evidence.

## Immediate pause / abort

Pause rollout on any of:

- HTTP 403;
- HTTP 429;
- `battlelog_throttle`;
- collection persistence failure;
- physical/terminal accounting anomaly;
- rolling-hour background starts above 1,296;
- historical bootstrap materialization;
- foreign/unexpected work consumed by production collectors;
- repeated ownership/lease corruption;
- database/revision/primary mismatch.

An ordinary classified temporary Battlelog failure follows normal retry policy
and is not by itself an abort.

## Rollback

Rollback is operational, not destructive:

1. drain the active production collector so it stops claiming new work;
2. stop the collector process;
3. stop/disable production materialization so later BF4SW observations cannot
   create additional production jobs;
4. preserve `collection_events` and `collection_state`;
5. run read-only inspection/audit;
6. inspect pending production queue provenance before deciding whether jobs
   remain for restart or require a separately designed cleanup.

Never bulk-delete queue work during an incident merely to make an audit green.
Never delete historical collection evidence as rollback.

## Restart after a pause

Do not simply restart after an abort signal. First identify and document the
cause, verify database/revision/primary, inspect queue ownership and pending
work, and rerun the applicable read-only audit. Resume materialization and the
collector only after the rollout decision is explicitly re-authorized.

## Stage 9A accepted dry evidence

As of the post-cleanup readiness checkpoint:

- full automated suite: 279 passed;
- Step 7 residue cleanup: accepted, 24 exact rows removed with events/state preserved;
- post-cleanup verifier: PASS;
- production collector daemon contract: behaviorally exercised;
- production drain/resume control: rollback-only live PostgreSQL exercise PASS;
- rollback exercise observed `drained=false -> true` inside the transaction and
  `false` again after rollback on a fresh connection;
- final activation readiness: PASS with zero background jobs, zero Step 7
  residue, zero claimed/running jobs, three exact frozen production collector
  identities, zero retired identities, and zero current jobs;
- checkpoint audit now requires both an event boundary and timezone-aware
  cutover, and rejects foreign/pre-cutover production background provenance.

The remaining non-database gate before Stage 9B is an explicit deployment
check that no other BF4PS discovery process is already running with production
materialization enabled.

On every host where BF4PS discovery is currently deployed or could already
have been manually started, run:

```bash
cd /opt/bf4-player-stats
.venv/bin/python scripts/phase5b_step9_materialization_process_check.py
```

The checker reads local `/proc` only. It performs zero database writes and
zero Battlelog requests, and fails if it finds a BF4PS discovery command line
containing `--materialize-production-jobs`. A PASS is host-local evidence;
do not treat a PASS on tcou as proof about another host.

## Stage 9A boundary

This runbook documents commands and semantics; it does not authorize executing
the production entrypoint or enabling materialization. Stage 9A remains a
zero-live-Battlelog phase until the external materialization-process check is
recorded and the implementation checkpoint is formally accepted.
