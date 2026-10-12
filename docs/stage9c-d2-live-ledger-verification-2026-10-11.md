# Stage 9C D2 live ledger and failed-soak read-only verification

Status: evidence checkpoint. BF4PS production deployment remains HOLD. No writes, migrations, HTTP, or ignition performed for this verification.

## Identity and schema (read-only PostgreSQL queries from tcou)

- Database: `bf4ps_scratch_stage9c_d2`; role: `bf4ps_stage9c_d2`; `pg_is_in_recovery() = false`; `transaction_read_only = off` (session setting; queries executed were SELECT only).
- Alembic revision: `0006_stage9c_soak_round_ledger`. The earlier `0004` integration-scratch verification document is NOT evidence for this database.
- Present ledger tables: `soak_runs`, `soak_rounds`, `soak_round_jobs`.
- `soak_runs` columns: run_id, cohort_digest, baseline_event_id, attempt_ceiling, site_attempt_ceiling, start_at, deadline_at, state, stop_reason, created_at, updated_at.
- `soak_rounds` columns: run_id, round_number, eligible_at, state, enqueued_at, completed_at.
- `soak_round_jobs` columns: run_id, round_number, soldier_id, job_id, outcome.
- Primary keys: runs(run_id), rounds(run_id,round_number), round_jobs(run_id,round_number,soldier_id). Unique: round_jobs(job_id). Foreign keys: rounds to runs; round_jobs to rounds; both ON DELETE RESTRICT.
- Constraints: rounds 1..12; run state prepared/running/stopping/completed/failed/stopped; round state planned/enqueued/completed/failed; job outcome pending/success/failed/abandoned. Run bounds and timestamp consistency checks present.

## Historical failed run (immutable evidence)

Run: `bf4ps-d2-three-hour-soak-20261011-v1`. State `stopping`, stop_reason `three-hour deadline reached`. Start 2026-10-11 20:44:40.543303 UTC; deadline 23:44:40.543303 UTC. Baseline event ID 109, global physical-attempt ceiling 108, site ceiling 36.

- Rounds 1-5 completed; round 6 enqueued; rounds 7-12 absent.
- 51 `collection_attempt_started` and 51 `collection_success` events after baseline: hnl-01 36, kah-01 12, tcou 3.
- Round 6: six jobs with exactly one physical start and one success each; jobs 778, 779, 780 still queued with zero physical starts/successes.
- Job 778: soldier 571, queue status running, attempt_count 1, lease_expires_at 2026-10-11 22:02:36.114804 UTC; no recorded physical start. This is a stale leased job, NOT evidence of an HTTP request or a success.
- Job 779: soldier 572, pending, attempt_count 0, no lease.
- Job 780: soldier 573, pending, attempt_count 0, no lease.
- The existing `inspect_round` reported `all_success=false`, `any_queued=true`, `anomalies=[]`. Its anomaly list does NOT mean the run is complete; it means no duplicate-success or missing-success anomalies of the kinds it detects.

## Recovery decisions and outstanding gates

Do not change the old run, revive job 778, reset the ledger, or replay any uncertain work. Do not mark the historical soak complete. Future soak requires fresh approved run ID and explicit authorization for real Battlelog requests.

Site-restricted job selection and cross-site HTTP gate are committed on `fix/stage9c-d2-soak-recovery`; full offline suite previously passed (829 tests at commit e3d696a). Before future live run: add durable terminal reconciliation/reporting with explicit incomplete/stale lease classifications; verify the full D2 schema against migrations (this checkpoint verifies ledger objects and constraints, not every application table); repeat offline suite; obtain operator go/no-go.
