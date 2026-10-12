# Stage 9C D3 Phase A controlled reset and three-site smoke — 2026-10-11 HST

Status: **PASS for bounded Phase A smoke only**. No multi-hour endurance claim; no live Battlelog HTTP; production BF4PS remains HOLD.

## Before reset

- Three-site D3 harness branch `fix/stage9c-d2-soak-recovery`, code commit `d744f0b`.
- Unit suite: 854 passed on tcou; D3-specific nine tests passed on tcou, kah-01 and hnl-01.
- Initial D3 state: 900 claimed jobs, 900 total attempts, zero cross-site ownership errors.
- Durable pre-reset JSON: `/root/bf4ps-d3-evidence/snapshot-97e289b3b9bb4550bee50596d97b88cc.json` (tcou).
- Full PostgreSQL custom-format backup: `/root/bf4ps-d3-evidence/pre-reset-900-claims-20261011.dump` (tcou), 118544 bytes; SHA-256 `81338fa8b7ac0a1fa98cef1238beeede27772ec0088edb13e019c027fe509810`.
- The first pg_dump invocation using a SQLAlchemy-style URL failed; a second invocation using parsed connection fields succeeded. No credential values belong in the documentation.

## Guarded reset

Command: `python -m scripts.stage9c_d3_endurance reset --execute --evidence-path <pre-reset-snapshot>` using the D3 environment and existing validation venv.

Result: 900 jobs reset; 3 collectors deleted. Immediate verification: 900 pending, attempt_sum 0, zero ownership violations. No D2 or production changes.

## Bounded physical-site smoke

Each site ran `worker --site <site> --seconds 30 --max-cycles 10 --run-id phasea-smoke-20261011` using the isolated D3 environment. Site invocations were **sequential**, not simultaneous.

| Site | Claims | Releases | Mean cycle latency |
| --- | ---: | ---: | ---: |
| tcou | 10 | 10 | 4.899 ms |
| kah-01 | 10 | 10 | 150.491 ms |
| hnl-01 | 10 | 10 | 123.949 ms |

All three workers produced local durable JSON evidence under `/root/bf4ps-d3-evidence/worker-phasea-smoke-20261011-<site>.json`.

Post-smoke verification: 900 pending jobs, attempt_sum 30, zero ownership violations. Post-run snapshot: `/root/bf4ps-d3-evidence/snapshot-d15d8f8c2dda4280bb74e370b60a39ae.json` on tcou.

## Limitations and next gates

- This run proves only bounded claim/release mechanics on three physical sites. It does **not** prove synchronized concurrent workers, sustained connection pressure, lease-expiry recovery, token-fencing under races, real statistics parsing/persistence, or hours-long stability.
- Before the 10-minute Phase B shakedown, review the worker's session-level advisory lock lifecycle and durable evidence on exceptions, then explicitly stage bounded concurrent work.
- No external Battlelog, Keeper or BFLIST requests were made.
