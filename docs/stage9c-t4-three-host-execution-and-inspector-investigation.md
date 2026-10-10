# Stage 9C T4 — three-host scratch race evidence and inspector investigation

**Operator execution:** 2026-10-10 UTC. **Status:** cross-host claim/cleanup PASS; time-sensitive budget inspector assertion unresolved; T4 formal closure OPEN; Stage 9C production HOLD.

## Test identity and boundaries

- Branch: `test/stage9c-admission-concurrency`; isolated checkout `/opt/bf4ps-stage9c-validation`.
- Scratch PostgreSQL: `mak-db-02.bf4statusbot.com` (`192.168.10.78`), database `bf4ps_scratch_stage9c_integration`, user `bf4ps_stage9c_integration`; expected Alembic `0004_stage9c_supervision_runs`.
- Three independent host processes: `tcou`, `hnl-01`, `kah-01`. No Battlelog/BF4 HTTP by the participants, no production activation.
- Successful shared run UUID: `709bc574-6ebf-4f05-adc9-e0fa3ae620a2`.
- Initial synthetic usage: 1,295 `collection_attempt_started` events, leaving one of 1,296 global slots.

## Operator-verified race and ledger

- Coordinator seed: jobs/soldiers `(45,45)`, `(46,46)`, `(47,47)`; barrier release: `PASS: three hosts ready; release committed`.
- `tcou`: READY, DONE DENIED; job 45 pending, attempt_count=0.
- `hnl-01`: READY, DONE WIN; job 46 claimed, attempt_count=1, collector `3a7c111a-7c18-4620-b056-10d59ca2a2c8`.
- `kah-01`: READY, DONE DENIED; job 47 pending, attempt_count=0.
- Read-only diagnostic: exactly three READY, one RELEASE, three DONE; 1,295 synthetic starts; no start event for winning reservation; total event rows 1,302.
- All three host-local process checks reported `No T4 participant running`.
- Evidence file captured on `tcou`: `/tmp/bf4ps-t4-success-709bc574.json` (operator-managed local artifact; not committed to Git).
- Guarded `cleanup --execute` with both operator attestations PASS; independent `diagnose --check` reported all five fixture tables empty and PASS.

## Inspector failure and working hypothesis

`scripts.phase5b_stage9c_t4_coordinator inspect --execute --run-id 709bc574-6ebf-4f05-adc9-e0fa3ae620a2` printed the expected one claimed/two pending jobs, then:

```text
USAGE BackgroundServiceUsage(total=1295, active=1295, bootstrap=0, recovery=0)
AssertionError: budget incorrect after winner reservation
```

Source audit of `bf4ps/background_service.py::_usage` shows the reserved-job query includes `j.lease_expires_at > now()` and excludes jobs with a matching physical-start event. The winner's lease was `2026-10-10 06:19:31.009215+00` to `06:21:31.009215+00`. The inspector unconditionally asserts `usage.total == 1296`, without checking whether the winning reservation's lease is still live. **A delayed inspect after 06:21:31 UTC would correctly count only 1,295 synthetic physical starts.** This is a source-grounded explanation, **not yet confirmed**: the exact inspection timestamp was not captured.

Do **not** change the production budget algorithm to count expired leases. A safe test correction should explicitly distinguish: (a) active unstarted winner lease → usage 1296; (b) expired unstarted winner lease → usage 1295, while retaining the committed one-winner/two-denied and ledger invariants. Prefer independent, time-controlled offline regression tests; review whether inspection can be made time-robust without weakening safety. Avoid changing frozen 1,296 rolling-hour policy.

## Next engineering gates

1. Check existing Stage 9C design, documented schema, migrations and budget tests against the above source reading.
2. Add deterministic tests for before/after lease expiry; confirm that the inspector assertion is the sole issue before any production-code change.
3. Correct only the scratch inspector/test expectation if validated, on a reviewable branch; run offline tests.
4. Decide whether a fresh scratch-only race is needed to validate corrected inspection; request separate operator approval for any new writes or remote participants.
5. Keep T5 physical-start ledger reconciliation and O1–O4 open; Stage 9C six-hour production trial NOT AUTHORIZED.

## Historical/operational caution

Earlier T4 attempts included an incorrect manually transcribed UUID and a partially seeded fixture that was safely recovered. Preserve historical output as evidence, but do not interpret zero marker-scoped rows as proof the whole scratch DB is empty; use independent `--check`. No future remote execution is implied by this record.
