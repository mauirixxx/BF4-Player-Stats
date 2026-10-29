# Battle Reports — discovery research (2026-10-28)

Status (2026-10-29): **bounded manual proof of concept with a deployed database on `reports`**; no unattended crawler or bulk ingestion enabled. The earlier research-only statements below describe historical milestones and are superseded by this status. Prioritize the existing ~6-million-record MySQL identity dump before other bulk imports.

## Verified on tcou via unauthenticated curl

Battlelog's HTML pages are shells; the useful data is fetched through JSON endpoints. Observed request times are *examples*, not performance guarantees: historical reports may time out (sometimes ~30 seconds), and pre-2018 reports may be missing after Battlelog's reported migration.

### Full round report

- Player-specific page: `https://battlelog.battlefield.com/bf4/battlereport/show/1/2112147262198514752/236753552/`
- General page: `https://battlelog.battlefield.com/bf4/battlereport/show/1/2112147262198514752/`
- HTML embeds `#battlereport-load-url`: `/bf4/battlereport/loadgeneralreport/2112147262198514752/1/0/`.
- Direct JSON: HTTP 200, 104,446 bytes, ~0.76 seconds. `players` dictionary contains **91 persona IDs**; teams have 40 and 51 participants. Fields include `personaId`, `persona.personaName`, `persona.clanTag`, EA user ID, round kills/deaths/rank/team/squad; report includes timestamp, server GUID, map, mode, platform. Example report server GUID `28773abe-e620-4d36-9512-c6f4b128f0ad`.
- PS4 full report: `/bf4/battlereport/loadgeneralreport/1383650491023205888/32/0/`; HTTP 200 JSON, 83,571 bytes, ~2.75 seconds; **74 players** (36 + 38), including persona `406653213`.
- **Xbox full-report roster retrieval remains untested** as of this document.

### Soldier report history

PS4 example: `https://battlelog.battlefield.com/bf4/soldier/KING-_-DYLAN666/battlereports/406653213/ps4/`

HTML contains `#profile-stats-fetch-url` pointing to:

`/bf4/warsawbattlereportspopulate/406653213/2048/32/`

HTTP 200, JSON, 9,052 bytes, ~0.58 seconds, **10 report summaries** from April 2021. `data.gameReports[]` has `gameReportId`, `createdAt`, map, server name, game mode, etc.

Xbox example: `https://battlelog.battlefield.com/bf4/soldier/deceptions56/battlereports/1680895792/xboxone/`

HTML points to `/bf4/warsawbattlereportspopulate/1680895792/2048/64/`; HTTP 200, 124,181 bytes, ~0.80 seconds; **10 report summaries**. Platform mapping observed: PC=1, PS4=32, Xbox One=64; game parameter 2048.

### Infinite-scroll pagination (Xbox verified)

`/bf4/warsawbattlereportspopulatemore/{persona_id}/2048/{platform}/{cursor}/`

Cursor is Unix timestamp in seconds. Starting from the initial batch, use `min(report["createdAt"] for report in batch) - 1`. For Xbox persona 1680895792, initial batch's oldest timestamp was `1757885399`. Querying cursor `1757885398` returned 10 *different* report IDs (zero overlap), HTTP 200, ~0.77 seconds. An arbitrary older cursor `1700000000` returned ten reports from November 2023. End-of-history behavior and stalled-cursor handling still need testing.

## Next controlled experiments

1. Fetch an **Xbox** report from history using `/bf4/battlereport/loadgeneralreport/{report_id}/64/0/`, verify roster names/persona IDs and team counts.
2. Fetch several **old reports** (e.g., 2021 PS4, 2023 Xbox, older PC examples) and record response status, time, completeness, and failures; do not assume 200 means complete JSON.
3. Test pagination to end-of-history on one low-volume soldier, recording empty response, repeats, or errors; verify PC/PS4 pagination too.
4. Determine whether pre-2018 reports consistently fail, without broad scanning.
5. Document HTTP timeout, retry/backoff, 403/429/5xx behavior, and request budget before scaling.

## Design constraints — avoid the trillion-branch tree

- Separate **soldier-history queue** (persona + platform + cursor) from **report-fetch queue** (platform + report ID). Use unique keys and idempotent inserts.
- Report participants seed *candidate* identities, not immediate full-stat collection or unrestricted recursive crawling.
- Deduplicate each report globally; a 91-person round should not trigger 91 duplicate report downloads.
- Bound expansion by maximum depth, daily new-soldier budget, daily report budget, per-host rate limit, and priority; persist frontier/checkpoints and provenance.
- Classify transient timeouts versus confirmed unavailable/deleted reports; exponential backoff with capped retries and a dead-letter state.
- Preserve persona IDs as authoritative, names as aliases, platform as part of identity; record discovered-at, report timestamp, source report ID, and parser version.
- Keep report crawler traffic separate from existing BF4PS collectors, but coordinate any shared Battlelog IP/rate-limit budget.
- No production DB writes or collector deployments until schema-first design, small soak tests, and explicit approval.

## Open questions

- Xbox roster retrieval and oldest available report behavior.
- Whether PS4 and PC history pagination exactly matches Xbox.
- Can report participants' histories be fetched with persona ID alone without a name?
- Are commander/spectator/duplicate roster entries included? Are roster IDs always stable?
- Whether `createdAt` cursor boundary is inclusive/exclusive under ties.
- How far historical data extends after the reported 2018 Battlelog migration.


## Follow-up validation (2026-10-28, tcou)

**Xbox full roster confirmed:** `/bf4/battlereport/loadgeneralreport/2058418070585130688/64/0/` returned HTTP 200, 91,568 bytes in 4.04 s; JSON platform=64, **79 players** (39 + 40), including persona `1680895792` named `deceptions56`. This closes the Xbox-roster open item above.

**Historical report fetches succeeded:**
- PS4 report `1379705792854707712` from April 7, 2021: HTTP 200, 88,651 bytes, 4.37 s, JSON platform=32 with **78 players**.
- Xbox report `1724222489168005376` from November 2023: HTTP 200, 98,313 bytes, 4.84 s, JSON platform=64 with **87 players**.

These are successful spot checks, **not** a reliability sample. We have not yet tested pre-2018 loss, timeouts across a large sample, or pagination termination. Do not infer historical availability rates from these three successes.


## 2018 boundary exploration (2026-10-28, tcou)

For PS4 persona `406653213`, `warsawbattlereportspopulatemore` returned 10 report summaries each for cursors at 2018-10-01, 2018-07-01, 2018-04-01, 2018-01-01 and 2017-12-31. Dates in those results were earlier than each cursor.

- **2018-12-31** report `1079881192119748160`: full JSON HTTP 200, 95,405 bytes, 4.03 s, 84 players; created 2018-12-31 23:41:36 UTC.
- **2017-12-31** report `947584453687928384`: full JSON HTTP 200, 101,500 bytes, 7.23 s, 91 players; created 2017-12-31 22:12:07 UTC.
- Cursors 2017-07-01, 2017-04-01, 2017-02-01, 2017-01-15, 2017-01-01, 2016-01-01, 2015-01-01 and 2014-01-01 returned zero report summaries **for this particular persona**. This is not proof that reports from those dates are globally absent.

**Conclusion:** Some pre-2018 reports remain accessible, contradicting an absolute global 2018 cutoff. Exact earliest surviving report and platform-wide availability remain unknown; a broader sample across soldiers/platforms is necessary. These successful fetches are not evidence of general reliability.


## Veteran PC account test — mauirixxx (2026-10-28, tcou)

Persona `236753552`, PC platform `1`. Soldier history page `/bf4/soldier/mauirixxx/battlereports/236753552/pc/` returned HTTP 200 and embedded `/bf4/warsawbattlereportspopulate/236753552/2048/1/`.

History cursor findings:
- Before 2019-01-01: 10 reports dated December 2018.
- Before 2018-01-01: 8 reports dated 2017-09-23 through 2017-12-24.
- Before 2017-01-01, 2016-01-01, 2015-01-01, 2014-01-01 and 2013-01-01: zero summaries for this persona, despite the user's known BF4 activity since 2013. **Do not interpret missing history as proof of no historical play.**

Crucial payload failure mode:
- 2017-09-23 report `911517592119201856`: HTTP **200**, 4-byte body **`null`**, 0.50 s. This is not a valid report despite HTTP success.
- 2017-11-19 report `932053209641301888`: HTTP **200**, 40,112 bytes, 5.70 s, valid JSON with **33 players**.

Crawler must classify JSON `null`, malformed JSON, and incomplete roster separately from valid success; treat a historical missing report as unavailable unless a retry policy establishes a transient condition. Some 2017 reports are accessible and others are not.


## 2026-10-29 — V1 schema approved; read-only curl smoke test

The approved identity-discovery schema is documented in [SCHEMA-V1.md](SCHEMA-V1.md). This supersedes the earlier research-only schema status **for design only**; no database migration or ingestion was deployed.

Read-only tests from `tcou` (three requests, no crawler):

- PC full report `2112147262198514752` on platform 1: HTTP 200, **4 bytes, JSON `null`**, 0.43 s. This URL had returned a full roster on October 28.
- Xbox full report `2058418070585130688` on platform 64: HTTP 200, **4 bytes, JSON `null`**, 0.45 s. This URL had returned a full roster on October 28.
- PC soldier history `/bf4/warsawbattlereportspopulate/236753552/2048/1/`: **curl timeout after 20 s with zero bytes received** (HTTP 000); no JSON file produced.

These results do **not** establish permanent report deletion, general Battlelog outage, or rate blocking. They establish that HTTP 200 alone is insufficient and that endpoint availability needs further controlled investigation. No identity records were imported. No server GUID or rename semantics could be verified from today's `null` responses.


## 2026-10-29 — bounded sequential versus concurrency-2 experiment (reports host)

Executed **on `reports`**, not tcou. Read-only Python 3.14 subprocess/curl probe: four previously documented full-report URLs (two PC, one PS4, one Xbox), one sequential pass with 1.5-second gaps, then a concurrency-2 pass in pairs with 3-second gaps. Eight requests total; each had a 5-second connect timeout and 12-second total timeout. Per-request classification and timings saved on `reports` at `/var/tmp/bf4reports-probe-20261029.jsonl`; script at `/var/tmp/bf4reports-probe.py`. No DB writes.

| Report | Sequential | Concurrent 2 |
|---|---|---|
| PC `2112147262198514752` | HTTP 200, JSON null, 3.90 s | HTTP 200, JSON null, 3.38 s |
| PC `932053209641301888` (2017) | HTTP 200, JSON null, 0.45 s | HTTP 200, **40,112-byte JSON potential report**, 3.68 s |
| PS4 `1379705792854707712` | HTTP 200, JSON null, 0.44 s | HTTP 200, JSON null, 0.43 s |
| Xbox `2058418070585130688` | HTTP 200, JSON null, 0.47 s | HTTP 200, JSON null, 0.44 s |

**1/8 potential success, 7/8 JSON null; no timeouts.** The successful response was classified by the presence of a `players` key; this run did not persist the full response for detailed field validation. A later retry succeeded after an earlier null, consistent with intermittent backend availability. This experiment **cannot establish** whether concurrency helped, whether retry timing helped, or a general success rate. Start with concurrency 2, bounded backoff/jitter, and strict payload validation. More measured samples needed before increasing concurrency.


## 2026-10-29 — live database and schema ownership locked

The authoritative deployed 11-table design and each table's sole duty are documented in [SCHEMA-V1.md](SCHEMA-V1.md). **`battle_reports` contains only fully imported reports.** `history_discoveries` holds report IDs to fetch; `battle_report_raw` preserves original validated JSON even if the structured import fails; `battle_report_download_attempts` holds aggregate retry state, not report content. The raw archive is intentionally separate to avoid treating partially processed reports as complete. No further tables were added for this decision.

Verified on `reports`, PostgreSQL database `bf4_battle_reports`: **3** `battle_reports`, **3** `battle_report_raw` rows, **3** `servers`, **170** `players`, **171** `report_players`, **170** `player_name_history`, **350** `history_discoveries`, **350** `history_report_sources`, **35** `history_pages`, **1** `history_checkpoints`, and **3** `battle_report_download_attempts`. These counts are a dated snapshot, not invariants. The new PC report `2115035533362014592` was successfully archived and imported, alongside the earlier PC and PS4 reports.

Manual scripts currently on **`reports` only**: `/var/tmp/bf4reports-history-persist.py`, `/var/tmp/bf4reports-download-test.py`, `/var/tmp/bf4reports-build-import.py`; schema SQL snapshots `/var/tmp/bf4reports-schema-v1.sql`, `/var/tmp/bf4reports-history-schema.sql`, `/var/tmp/bf4reports-download-schema.sql`. They are **not** production-installed or committed source; `/var/tmp` is temporary. Do not run multiple downloader instances because the test importer uses shared fixed filenames. The importer still needs A→B→A name-transition handling and stronger atomicity/error recovery before unattended use. All Battlelog operations for this project must run on `reports`, not `tcou`.

Next gate: move reviewed code and migrations into this repository, test raw archive → relational import idempotence and rollback, repair name-history semantics, and then design controlled scheduling and pacing. Preserve existing raw JSON and history responses during all migrations.


## 2026-10-29 — manually triggered downloader smoke test

Installed on `reports`: `/opt/bf4reports/bf4reports.py`, with executable wrapper `/usr/local/bin/bf4reports`. Usage: `bf4reports download --limit 20 --attempts 3 --delay 4` (manual only; **no timer/cron/service**). It uses an exclusive local process lock; selects unimported raw archives first, then undiscovered-in-archive report candidates; validates report identity/server/roster; commits valid full JSON to `battle_report_raw` **before** attempting relational import; performs the five core-table writes plus `imported_at` in one PostgreSQL transaction; tracks retries and uses jittered exponential backoff. Each run is bounded by the limit; reports already fully imported are skipped. No shared temporary import files are used. Name history now compares the latest observed transition rather than treating a previously seen name as permanently ineligible, supporting A→B→A in new observations. Historic observations imported out of order remain a limitation requiring dedicated tests.

**Verified smoke test:** `bf4reports download --limit 1 --attempts 1` fetched and imported PC report `2115026357147609472` with 71 participants; summary `new_imported=1, failed=0`. Live post-test counts: 4 `battle_reports`, 4 `battle_report_raw`, zero raw rows awaiting import, 202 `players`, 242 `report_players`. This verifies one happy-path report, **not** comprehensive failure recovery, rename history, multi-platform parity, or sustained pacing. Production code currently resides on `reports`, not yet version-controlled; promote it to the repository and add automated tests before unattended operation.


## Manual downloader — retry cooldown and source control (2026-10-29)

The manually invoked downloader is tracked on `main` at [`battle-reports/bf4reports.py`](./bf4reports.py), matching the installed `/opt/bf4reports/bf4reports.py` on `reports`. Run with `bf4reports download --limit 20 --retry-cooldown-minutes 30`. The default cooldown is 30 minutes, applied to previously attempted reports before selecting them for a new batch. It uses the existing `battle_report_download_attempts.last_attempt_at` and `last_result` columns; no schema migration. Reports are never discarded because of cooldown. The error diagnostics distinguish Battlelog JSON `null`, non-object responses, missing report identity, and mismatched identity. A smoke test using `--limit 1 --attempts 1 --retry-cooldown-minutes 10080` correctly reported a retryable JSON `null` response. This is manual-only; no scheduled downloader was enabled. GitHub updates are currently made via the connected GitHub integration, so local Git/SSH authentication on `reports` is optional.
