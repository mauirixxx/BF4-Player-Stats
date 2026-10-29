# Battle Reports — discovery research (2026-10-28)

Status: **research/proof of concept only**. No production crawler, schema migration, or ingestion authorized. Prioritize the existing ~6-million-record MySQL identity dump before other bulk imports.

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
