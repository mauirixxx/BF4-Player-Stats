# Battle Reports — V1 logical schema (2026-10-29)

**Deployed schema and table-duty contract (2026-10-29).** Independent PostgreSQL 18 database `bf4_battle_reports` on `reports`; BF4PS PostgreSQL 16 remains untouched. Branch: `main`. The five original relational tables are joined by six explicitly scoped discovery/archive/operational tables. No unattended crawler is enabled.

## Purpose
Discover new player identities and preserve **who played with whom, on which server, and when**. No per-round statistics, teams, kills, deaths, scores, ranks or winner data. Identity is `(platform, persona_id)`. Battlelog platform codes observed: PC=1, PlayStation=32, Xbox=64.

## Five core tables (fully imported data only)
- **servers**: `id bigint PK`, `server_guid uuid UNIQUE NOT NULL`, `current_name text`. Stable GUID is king; missing GUID means reject the report. Name may be updated as newer observations arrive. Confirm payload GUID formatting before final migration.
- **battle_reports**: `id bigint PK`, `platform smallint NOT NULL`, `battlelog_report_id bigint NOT NULL`, `server_id bigint NOT NULL REFERENCES servers`, `report_timestamp timestamptz NOT NULL`, `collected_at timestamptz NOT NULL`. Unique `(platform,battlelog_report_id)`. Timestamp of report and timestamp of collection are different. Confirm report timestamp field semantics from payload.
- **players**: `id bigint PK`, `platform smallint NOT NULL`, `persona_id bigint NOT NULL`, `current_name text`, `current_name_observed_at timestamptz`, `earliest_report_at timestamptz`, `latest_report_at timestamptz`. Unique `(platform,persona_id)`. Earliest/latest are MIN/MAX **report timestamps**, not fetch timestamps. Current name changes only on a newer name observation.
- **report_players**: `report_id bigint REFERENCES battle_reports`, `player_id bigint REFERENCES players`, `player_name_observed text`, composite PK `(report_id,player_id)`. Name is a **snapshot from the retrieval** and must never be rewritten on subsequent player rename. It does not claim to be the name at the time of the round.
- **player_name_history**: `id bigint PK`, `player_id bigint REFERENCES players`, `player_name text NOT NULL`, `observed_at timestamptz NOT NULL`, optional source report ID. Append transitions, including A→B→A, preserving historical observations. First/last seen aggregates can be derived; do not collapse distinct change events.

## Operational rules
- Report requires valid platform, report ID, report timestamp, server GUID and usable participant identities; no GUID, no admission. Reject malformed, incomplete, or HTTP 200 JSON `null` responses and log failure class separately.
- Idempotent report and participation inserts; the same report may be discovered through many soldiers.
- Store current names from observations; never overwrite an earlier report's `player_name_observed`. Use collection observation ordering, not report age, to determine current names. Keep conflicting observations auditable.
- Server-name historical snapshots are not required in V1; test whether Battlelog returns current server name for old reports.
- Operational history/report queues, retry states, bounded discovery expansion and request pacing are separate from the five core tables.
- BF4PS integration is **future only**: one-way deduplicated `(platform,persona_id)` identity admission, matching existing BF4SW→BF4PS behavior, respecting exclusions, existing queues and rate limits. No direct writes to BF4PS tables.
- Preserve every successfully retrieved valid full-report payload in `battle_report_raw`, including payloads whose relational import fails. Do not delete archive rows as part of normal retries.

## Six discovery, archive, and operational tables (deployed)

| Table | Primary key | Sole responsibility | Not its responsibility |
|---|---|---|---|
| `history_discoveries` | `(platform,battlelog_report_id)` | Deduplicated directory of report IDs found in player-history summaries, with reported time, server name/map hint and first/last discovery timestamps | A fully downloaded or imported report |
| `history_report_sources` | `(platform,persona_id,battlelog_report_id)` | Provenance: which player history exposed a report; references `history_discoveries` | Player participation proof; use `report_players` for verified full-report roster membership |
| `history_pages` | `(platform,persona_id,cursor_used)` | Preserve each successful history-page response and pagination metadata (`raw_response`, retrieval time, count, next cursor) | Full battle-report payloads |
| `history_checkpoints` | `(platform,persona_id)` | Durable next cursor and progress for restarting each player's history scan | Report download status |
| `battle_report_raw` | `(platform,battlelog_report_id)` | Preserve complete validated full-report JSON as soon as received; `fetched_at` and nullable `imported_at` record archive/import lifecycle | Substitute for the normalized report/roster tables; a row here does **not** prove import succeeded |
| `battle_report_download_attempts` | `(platform,battlelog_report_id)` | Durable attempt counter, last attempt time, and last result for retry scheduling and diagnosis | Detailed HTTP request logs, downloaded JSON, or proof of a fully imported report |

**Contract:** `battle_reports` contains **only fully imported, validated reports** with a server and participating players. `battle_report_raw` is the loss-prevention archive, including valid JSON not yet imported. Their matching platform/report-ID values are intentional references, not duplicate storage of the same information: `battle_reports` has relational metadata; `battle_report_raw` has the original JSON. `history_discoveries` is only a candidate list and can have IDs absent from both other tables. A history summary is not sufficient to insert into `battle_reports`.

**Lifecycle:** player history → `history_pages` + `history_discoveries` + `history_report_sources` + `history_checkpoints` → paced full-report fetch (attempts tracked) → validate full payload → **commit raw JSON** to `battle_report_raw` → transactionally import `servers`, `battle_reports`, `players`, `report_players`, `player_name_history` → set `battle_report_raw.imported_at` only on successful import. Failed import must leave the raw payload intact and retryable; `null`, HTTP errors, incomplete JSON and missing required identities must not enter the raw archive as valid reports. No duplicate report imports across overlapping player histories.

**Current implementation limitations:** The test downloader uses fixed temporary paths and is single-process only; do not run concurrent instances. The initial name-history importer needs correction to record A→B→A transitions. The legacy first ten history pages contain reconstructed summaries rather than the original full response; newer pages preserve full JSON. `battle_report_download_attempts` currently stores aggregate attempts and the latest outcome only; do not describe it as a full event log. No automatic queue worker, dead-letter scheduler, or global rate-limit service is deployed.

**Schema change policy:** Before adding, dropping, or repurposing tables/columns, document the exact data ownership, lifecycle, migration and rollback here, then apply a reviewed migration. Preserve archived JSON and existing history pages. Keep the five original relational tables focused on successfully imported data. No new table is needed for the current three-report downloader test.

## Implementation gates
1. PC and PS4 full-report payload paths validated in small tests; Xbox full-report ingestion still needs end-to-end import validation.
2. Run a small read-only HTTP test; validate bodies, not HTTP status alone.
3. Deployed initial relational, history, and raw/archive tables on `reports`; any further migration requires review and documentation first.
4. Test name-change semantics and server rename assumptions as evidence permits.
5. Bounded manual test ingestion is active; no unattended production crawler or unbounded recursion without separate approval.
