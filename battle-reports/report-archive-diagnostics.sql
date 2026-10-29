-- Applied on reports, bf4_battle_reports, 2026-10-29.
-- Store complete successfully fetched Battlelog report payloads independently of normalized player/server records.
CREATE TABLE IF NOT EXISTS battle_report_details (
 platform smallint NOT NULL,
 battlelog_report_id bigint NOT NULL,
 report_json jsonb NOT NULL,
 extracted_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(platform,battlelog_report_id)
);
INSERT INTO battle_report_details(platform,battlelog_report_id,report_json)
SELECT platform,battlelog_report_id,raw_response FROM battle_report_raw
ON CONFLICT DO NOTHING;

-- One row per network attempt; retain even HTTP 200 / JSON null, invalid JSON, and error HTML.
CREATE TABLE IF NOT EXISTS battle_report_fetch_log (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 attempted_at timestamptz NOT NULL DEFAULT now(),
 platform smallint NOT NULL,
 battlelog_report_id bigint NOT NULL,
 attempt_number integer NOT NULL,
 outcome text NOT NULL,
 http_status integer,
 curl_exit integer,
 elapsed_ms integer,
 response_bytes integer,
 content_type text,
 error_message text,
 response_body text,
 response_truncated boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS battle_report_fetch_log_lookup
 ON battle_report_fetch_log(platform,battlelog_report_id,attempted_at DESC);
