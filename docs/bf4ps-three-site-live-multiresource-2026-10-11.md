# BF4PS — three-site live weapons + vehicles (2026-10-11)

**PASS.** Nine real PC soldiers, two resources each, three physical collectors sharing one isolated PostgreSQL database.

- Nodes: `tcou`, `kah-01`, `hnl-01`; each collected three weapons and three vehicles jobs.
- Database: `bf4ps_scratch_stage9c_d2` on `mak-db-02.bf4statusbot.com`, role `bf4ps_stage9c_d2`, revision `0005_stage9c_dispatch_ledger`.
- Follow-up to documented 9/9 detailed ignition; pre-existing events IDs 33–50, immutable attempt baseline event ID **50**; global limit **18** resource attempts.
- Script: `scripts/stage9c_three_site_live_multiresource.py`; explicit `--execute` for preparation and worker runs; no automatic retries.
- Preparation inserted 18 jobs; collector identity and egress keys preserved from the original ignition. Three remote processes ran concurrently.
- All nodes exited 0: `tcou` 51.49 s, `kah-01` 69.09 s, `hnl-01` 70.52 s.
- `verify` reported `VERIFY new_events=36 jobs=0` and `THREE-SITE LIVE MULTIRESOURCE PASS`.
- Each of the 18 soldier/resource combinations had state `success`, persisted rows >0, exactly `collection_attempt_started` then `collection_success`, and matching collector UUID; no outstanding queue job.

| Node | Soldier | Weapons | Vehicles |
|---|---|---:|---:|
| tcou | It_Mip | 174 | 82 |
| tcou | malilahygge | 173 | 82 |
| tcou | JonNZzin | 174 | 82 |
| kah-01 | GORBON_TREEMAN | 174 | 82 |
| kah-01 | stelyo_berberaks | 174 | 82 |
| kah-01 | pirulaconcaca | 173 | 82 |
| hnl-01 | yukonsunshine | 173 | 82 |
| hnl-01 | FrankoPop | 173 | 82 |
| hnl-01 | MLGPILLO | 173 | 82 |

## Race and baseline lessons

- The first `kah-01` and `hnl-01` launch hit a harness-only preflight race: `tcou` had already written resource events, while the preflight expected exactly 18 total events. Those two launches stopped without HTTP. The harness was corrected to validate only detailed-ignition events through the fixed baseline event ID. Commit `5ef9753`.
- Initial preflight incorrectly conflated event count 18 with last event ID 50; corrected to baseline 50 before any multi-resource HTTP was issued. Commit `0463fa0`.
- Initial preparation output printed an obsolete baseline label 18; corrected in the GitHub script. The actual request budget used 50 throughout execution.

## Boundaries

This verifies concurrent multi-resource live collection and persistence across three sites, with 18/18 successful jobs and correct event attribution. It does **not** yet prove dynamic work stealing, node-loss recovery, ambiguous-request crash safety, mixed-platform distributed collection, or multi-hour live soak. The work was isolated to D2; production BF4 Server Watcher remains untouched and production activation remains HOLD.
