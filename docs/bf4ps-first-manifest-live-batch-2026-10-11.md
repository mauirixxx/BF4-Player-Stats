# BF4PS — first manifest-driven live five-soldier resource batch (2026-10-11)

**PASS. Production HOLD unchanged.**

## Run identity and safeguards

- Host `tcou`; isolated database `bf4ps_scratch_stage9c_integration`, role `bf4ps_stage9c_integration`, revision `0004_stage9c_supervision_runs`.
- Existing collector `live-persistence-validation-tcou`, background production-budget admission and 10-second shared egress gate.
- Manifest `/root/bf4ps-d2-tests/live-five-pc-resources-manifest.json` on tcou; five known PC identities; resources `weapons` and `vehicles`; immutable starting `collection_events.event_id=24652`; ceiling 10 attempts.
- Implementation `scripts/stage9c_manifest_batch.py` at commits `8a48d99` and `4d09666`.
- Manifest initialization verified exact DB identity, writable state, schema revision, collector and cohort identities. It made no HTTP requests.
- The run completed in **91.52 seconds**, exit code 0, 10 successful collector results, and `MANIFEST LIVE BATCH PASS attempts=10/10`.

## Persisted rows

| Soldier | Soldier ID | Weapon rows | Vehicle rows |
| --- | ---: | ---: | ---: |
| KamiPebble | 52 | 173 | 82 |
| MANHUNT1999 | 53 | 173 | 82 |
| HyperMaxZ | 54 | 174 | 82 |
| LevchenkoBIKS | 55 | 173 | 82 |
| Peruvian_Baker | 56 | 174 | 82 |

All 10 resource states `success`; all 10 jobs finalized. Separate `verify` command confirmed each soldier/resource had exactly one `collection_attempt_started` and one `collection_success` event, with persisted rows and no remaining queue jobs.

After a follow-up fix, invoking `run` again with the same completed manifest returned:
`NO-OP: all resources already collected; attempts=10/10`
without new collection or re-queuing.

## Engineering caveats

This proves bounded happy-path live execution and a completed-batch no-op. It **does not yet establish full restart safety** for all crash points. Specifically, an interrupted run with an ambiguous physical outbound request, an expired lease, or a persisted failure must be tested before claiming reliable automatic resume. The current runner intentionally refuses non-pristine failed resources; it does not silently retry them. The manifest currently targets existing identities only; idempotent new-soldier registration is still to be implemented.

Eight total live soldiers now have detailed, weapon and vehicle statistics persisted, spanning PC, PS4 and Xbox One. Do not activate production until failure/restart gates pass.
