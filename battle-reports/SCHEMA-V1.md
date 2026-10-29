# Battle Reports — V1 logical schema (2026-10-29)

**Approved design; no SQL migration or crawler deployed.** Independent PostgreSQL 18 database on `reports`; BF4PS PostgreSQL 16 remains untouched. Branch: `main`.

## Purpose
Discover new player identities and preserve **who played with whom, on which server, and when**. No per-round statistics, teams, kills, deaths, scores, ranks or winner data. Identity is `(platform, persona_id)`. Battlelog platform codes observed: PC=1, PlayStation=32, Xbox=64.

## Five core tables
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
- Optionally keep bounded raw JSON samples for parser debugging, separate from core relational tables.

## Implementation gates
1. Confirm actual PC/PS4/Xbox payload field paths, server GUID, roster identity/name and report timestamp.
2. Run a small read-only HTTP test; validate bodies, not HTTP status alone.
3. Design migration and indexes from observed payloads; review before creating tables.
4. Test name-change semantics and server rename assumptions as evidence permits.
5. No production ingestion or unbounded recursion without separate approval.
