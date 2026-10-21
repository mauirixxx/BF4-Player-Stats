# BF4PS Phase 3D three-host distributed validation

Status: **PASS — normal three-host distributed collection proof complete**

Date: 2026-10-04 UTC

Design reference: `docs/phase3-distributed-collector-design.md`

Frozen topology: `docs/phase3d-frozen-topology.md`

Execution runbook: `docs/phase3d-two-host-runbook.md`

Final reconciliation harness: `scripts/phase3d_reconcile_live.py`

## Result

Phase 3D proved that three BF4PS collector processes on three physical hosts can safely compete for one PostgreSQL-coordinated `detailed/background` queue while using stable collector identities and independent BF4PS request gates.

The frozen 36-soldier cohort completed with:

- 36 terminal collection attempts
- 36 successes
- 0 collection failures
- 0 HTTP 403 results
- 0 HTTP 429 results
- 0 classified Battlelog throttle results
- 36 unique soldiers
- 36 unique logical jobs
- every attempt number exactly 1
- 12 attempts attributed to each collector
- final `detailed/background` queue empty
- all three collectors cleanly stopped
- operator controls preserved
- all three request gates materialized
- all 36 frozen soldiers in successful detailed collection state

The final read-only global reconciliation returned `BF4PS PHASE 3D GLOBAL RECONCILIATION: PASS`.

## Physical collectors

| Host | Collector | Collector UUID | BF4PS egress key | Attempts | Result |
| --- | --- | --- | --- | ---: | --- |
| `hnl-01` | `phase3d-hnl-01` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3d001` | `phase3d-hnl-01` | 12 | 12 success |
| `kah-01` | `phase3d-kah-01` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3d002` | `phase3d-kah-01` | 12 | 12 success |
| `tcou` | `phase3d-tcou` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3d003` | `phase3d-tcou` | 12 | 12 success |

Honolulu consumed the first 12 PC jobs before the other two hosts entered. `tcou` and `kah-01` then overlapped against the remaining 24 jobs and divided the PS4/Xbox work without duplicate execution. The final result remained exactly 12 attempts per host; this distribution was an observed result, not a static host/platform partition.

## Concurrent queue evidence

When `tcou` entered it observed 24 frozen jobs remaining. When `kah-01` entered shortly afterward it observed 23, showing that the shared queue had already changed through another physical collector.

The two collectors subsequently interleaved claims from the same remaining queue. PostgreSQL coordination produced 24 distinct logical jobs and soldiers across those two processes with no duplicate execution.

Together with Honolulu's earlier 12 jobs, global reconciliation proved exact coverage of the frozen 36-soldier cohort.

## Startup-race discovery and correction

The first launch exposed a harness assumption rather than a scheduler ownership failure.

After `hnl-01` started consuming the armed queue, the original worker startup guard caused `tcou` and `kah-01` to refuse startup because the queue was no longer pristine pending work. This guard was appropriate for a single-process preflight but incorrect for a distributed worker joining an already-active bounded run.

Commit `8487c57` (`fix: allow concurrent Phase 3D worker startup`) corrected the worker guard so a late-arriving collector can join the still-bounded frozen queue safely.

The experiment was not reset. Honolulu's 12 successful jobs were preserved, then the corrected `tcou` and `kah-01` workers joined the partially consumed queue and completed the remaining 24 jobs. This provides additional evidence that a collector can safely join a distributed workload after another collector has already begun processing it.

## Final database reconciliation

Commit `70ee67b` added the read-only `scripts/phase3d_reconcile_live.py` harness. It performed zero Battlelog requests and zero database writes.

Observed global validation:

- expected BF4PS test database: PASS
- writable PostgreSQL primary: PASS
- expected Alembic head `0003_request_gates`: PASS
- exactly 36 terminal attempt events: PASS
- exactly 36 collection successes: PASS
- zero collection failures: PASS
- zero 403/429/throttle signals: PASS
- exactly 36 unique soldiers: PASS
- exact frozen cohort covered: PASS
- exactly 36 unique logical jobs: PASS
- attempt numbers all exactly one: PASS
- all three collectors attempted 12: PASS
- all event identity snapshots match frozen hosts: PASS
- `detailed/background` queue finalized: PASS
- all three collector rows present: PASS
- all collectors cleanly stopped: PASS
- operator controls preserved: PASS
- all three request gates materialized: PASS
- all 36 detailed collection states successful: PASS

## Network and naming conclusions

Cross-site BF4PS database configuration must use the database FQDN `mak-db-02.bf4statusbot.com`. Short name `mak-db-02` did not resolve from Honolulu or Kahului during Phase 3D reconnaissance, while the FQDN resolved and PostgreSQL connectivity succeeded after the required `pg_hba.conf` host access was added.

`tcou`, `hnl-01`, and `kah-01` had three observed public IPv4 egress addresses during this proof. However, collector identity, BF4PS request-gate identity, and actual public NAT identity are separate concepts and must remain separate in runtime design.

In particular, `tcou` shares its public egress with BF4 Server Watcher host `mak-01`. The Phase 3D BF4PS request gate coordinates BF4PS traffic only and does not coordinate independent BF4SW traffic on that public address.

## Scope conclusion

Phase 3D answers the bounded distributed-correctness question: multiple physical BF4PS collectors can safely compete for and finalize one shared PostgreSQL work queue.

It does **not** establish the maximum safe Battlelog request rate, prove long-duration endurance, or prove BF4PS/BF4SW shared-egress coexistence under load. Those remain separate controlled experiments.

The normal three-host distributed collection proof is complete and is retained as the implementation baseline for the next distributed-runtime phase.
