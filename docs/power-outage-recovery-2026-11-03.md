# BF4PS power-outage recovery inventory (2026-11-03)

This is a recovery record, not a deployment approval. No production schema or service changes were made during inventory.

- GitHub `main` observed at `e64de24` and `feature/compact-rank-snapshots` at `f12bd05`. The persistent RNT-01 checkout was fast-forwarded to the latter, with a clean working tree before this record.
- The temporary RNT-01 checkout `/tmp/bf4ps-compact-final` vanished during the reboot. Its locally committed work `6d85903` (reader freshness and concurrency/fencing tests), `a770cef` (bounded block page fast path), and `31bfaba` (division benchmark) was not found in the checked repositories or the GitHub feature branch. Earlier real-data parity work from that temporary checkout may also be absent; compare the documented feature history before reconstructing.
- The lost fast-path implementation was benchmarked on 214,779 real PC vehicle rankings, 24 HTTP requests, eight concurrent clients, with p50 61 ms, p95 97 ms, maximum 98 ms. The legacy full-scan baseline was p95 6.4 s. These are historical observations, not a fresh post-reboot rerun.
- Migration `0022_compact_blocks_only_format.py` is absent from the currently fetched GitHub feature branch; production remains at migration `0021_reconcile_player_exclusions`. Do not apply a reconstructed migration without reviewing current schema reference and Alembic migrations.
- TCOU's live website working tree was preserved separately on GitHub branch `recovery/tcou-live-20261103`, commit `52bfd2469e33c7ca3a6ed8d9abdde2a2b3a1d1c7`. This is a recovery checkpoint, not a reviewed merge. The original TCOU branch and working tree were left unchanged.
- Reconstruct and test the missing feature changes in a persistent directory, reconcile them with the current GitHub feature branch, then push. Do not fast-forward `main` or enable production compact reads solely from this inventory.
