# General leaderboard opt-in website reader

Status: implemented on RNT-01 scratch; **not activated in production**.

The website API endpoint `/general-leaderboard` accepts the existing metric,
platform, page, page_size, search and division parameters.

Set `BF4PS_GENERAL_RANK_SNAPSHOT_READS=1` in the website process environment
to read the latest published generation. The default is disabled. The website
uses a read-only REPEATABLE READ transaction for snapshot reads and retains
the existing live reader when a published generation is unavailable.

Snapshot responses include `rank_source=published_snapshot`,
`generation_id`, `published_at` (ISO 8601) and
`rank_updated_at` (same timestamp for existing UI conventions).
Legacy responses include `rank_source=live`. Snapshot-mode requests bypass
the legacy first-page cache to prevent stale moderation exclusions. The
existing live-mode first-page cache retains its 300-second TTL.

The general ranking snapshot reader uses existing trigram-indexed name
and alias tables and preserves as-of rank, position, division and population.
Currently active exclusions are hidden on every snapshot read, including
the first page. The legacy cache behavior remains unchanged.
No website presentation has been activated yet.

Deployment gates: HTTP integration tests,
published/legacy fallback tests, full-scope writer timing, WAL/replica
monitoring, retention policy, and a one-node canary before fleet rollout.
Do not enable the flag before migration 0026 is deployed and verified.

## Isolated HTTP smoke test (2026-11-16)

RNT-01 PostgreSQL scratch (port 5542; 560,000 synthetic soldiers) passed
real localhost HTTP requests for the snapshot first page (generation 4,
10 rows), indexed name search (111 matches), and the legacy path when the
feature flag was disabled. The test harness changes the production database
name guard **only in an in-memory copy** of the handler; repository code and
production safeguards remain unchanged. Run the opt-in scratch harness via
`website/tests/scratch_general_rank_http_smoke.py` with the scratch database
URL and website API import path. The harness is not a production test.
