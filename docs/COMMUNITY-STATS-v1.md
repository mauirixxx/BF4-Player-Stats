# Community Statistics v1 — 2026-10-15

## Status

**Deployed** at https://www.bf4playerstats.com/community.html. This is a working, read-only first stage of the community aggregator. The incremental per-soldier contribution table and transactional change-feed design remain **future work**, not implemented.

## User-approved decisions

- Existing three header links stay in their original row. COMMUNITY STATS is a second-row link.
- Default platform ALL; filters PC, PlayStation (ps4), Xbox (xboxone).
- Include each metric as soon as its source data is successfully collected; do not require all four resources for a soldier.
- Browser refresh interval **60 seconds**.
- Avoid full scans per page view. Website reads a static JSON snapshot.
- Never count historical snapshots or aliases as additional soldiers.

## Current implementation

- `api/community_export.py` performs a single read-only grouped aggregation of **latest** `public.detailed_stats_current` joined to `public.soldiers`, with separate platform soldier counts. Each soldier contributes once.
- A dedicated `bf4ps-community-export.timer` triggers the oneshot service about every 60 seconds. Service reads the existing secret environment file on tcou, connects through `db.bf4statusbot.com` (as configured), enforces a 25-second SQL timeout, and atomically replaces `community-stats.json`.
- `site/community.html` fetches only this ~2 KB JSON; visitors do not issue SQL queries.
- Combined ALL totals are computed from the three platform totals, preventing divergence.
- Aggregate K/D = total kills / total deaths. Accuracy = total shots hit / total shots fired. Combined playtime = sum seconds / 3600. Zero denominators return zero.
- Source coverage: `detailed_soldiers` is explicitly displayed; only detailed-stats metrics are shown in v1. Weapon and vehicle aggregates will be added after their fields and semantics are separately verified.
- Counts reflect indexed BF4PS soldiers, not all BF4 players over the game's lifetime.

## Operational checks

`systemctl status bf4ps-community-export.timer`

`systemctl status bf4ps-community-export.service`

`journalctl -u bf4ps-community-export.service -n 20 --no-pager`

`curl -fsS https://www.bf4playerstats.com/community-stats.json`

Do not add secrets to the repository or serve the environment file. If a refresh fails, the last valid snapshot remains available and its timestamp exposes staleness.

## Incremental aggregation follow-up

The v1 exporter scans the current detailed-stats rows once per minute, **not on each page request**. This is bounded and currently fast at ~23k detailed records, but is not the eventual incremental table. Before implementing incremental writes:

1. Verify schema documentation against live `detailed_stats_current`, `collection_state`, and future weapon/vehicle source tables.
2. Design `community_soldier_contributions` keyed by soldier_id and `community_aggregate_checkpoint` with per-platform sums. Use transactional delta updates and checkpointing to survive restarts and failovers without double counting.
3. Benchmark backfill and delta maintenance against a scratch database, including the named regression **The Hamster That Counted Twice** (repeat a snapshot and prove totals do not change).
4. Reconcile against full source totals and measure lock contention before enabling writes in production.
5. Consider extending the snapshot exporter to read the aggregate table, then retiring the 60-second grouped scan.

The collectors' production transaction paths are unchanged by this release.
