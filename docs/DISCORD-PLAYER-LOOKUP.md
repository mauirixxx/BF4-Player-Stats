# `/pstats player` — initial exact-name lookup

The initial public player lookup is `/pstats player name:<exact name> platform:<PC|PlayStation|Xbox>`.

It searches the **current** soldier name only, case-insensitively, using the existing `ix_soldiers_current_name_lower` index and a platform filter. No substring search, autocomplete, historical alias search, or fuzzy matching. The verified live schema has `soldiers(current_name,platform,persona_id,last_seen_at,soldier_id)`; platform values are `pc`, `ps4`, and `xboxone`. The read-only query has a 4-second server-side statement timeout, a 4-second connect timeout, and LIMIT 2 to detect duplicate current-name matches rather than selecting an arbitrary identity.

Success displays a public detailed-statistics overview (or `Player not found` for zero matches); multiple matches report ambiguity. Role and channel restrictions apply to ordinary users; guild owner and configured management role bypass them. Denials are private.

The bot reads `BF4PS_STATS_DSN` separately from `BOT_DATABASE_URL`. A newly created container is required to load the environment variable. Do not commit credentials. Test a known name, a missing name, and the permission restrictions in Discord after deployment.

## Detailed overview (live on MAK-01 and RNT-01, 2026-10-22)

The player command now joins the exact-name match to `detailed_stats_current` using a bounded `LEFT JOIN`. It reports rank, time played, kills, deaths, K/D, accuracy, highest streak, KPM, SPM, wins/losses, win rate, and best class (highest class score). Undefined values show an em dash rather than invented zeros. Statistics are collected snapshots, not live Battlelog reads. No weapons or vehicles are queried. This implementation uses a native Discord embed. Operator live-tested `mauirixxx` and `FooeY` successfully on 2026-10-22; the displayed statistics came from BF4PS snapshots. Weapon and vehicle views remain future work.


## Planned rendered overview and direct refresh (2026-10-22 checkpoint)

Operator-approved target: a 960 x 600 PNG overview rendered by the Discord bot, retaining the exact-name/platform lookup and the current statistics. Replace the rank-icon area with the player's single highest-kill equipment item, selected by comparing the highest weapon kills and highest vehicle kills; include the equipment name, kills, and the website's existing fancy artwork. The website mapping is `website/site/equipment-artwork.js`, with files under `website/site/assets/equipment/`. Missing artwork must not prevent the overview. Tie-breaking must be deterministic.

Below the PNG, provide a Discord-native **Refresh Stats** interaction and a separate **Player Dossier** URL button. Dossier routing observed on the deployed website: `soldier.html?id=<soldier_id>` (ID must be obtained from the verified player lookup, not persona ID). The refresh interaction must be private to the clicker and must reuse the existing admission/cooldown system, not call Battlelog directly. A refresh must be denied if the soldier was successfully collected or manually refreshed within the previous 60 minutes. Race-safe enforcement belongs in the database-backed manual admission function, not only the Discord UI.

Live investigation: TCOU's `bf4ps-manual-api` service is active and bound to `127.0.0.1:8789`. It requires a private token and an allowed Origin. MAK-01/RNT-01 therefore **cannot safely call this endpoint directly** without a separately designed authenticated private network path. Do not expose the service publicly or copy its privileged DB credentials into the Discord bot. The current read-only Discord DB role must remain read-only.

**Not implemented or deployed as of this checkpoint.** The current native Discord embed remains operational. Before schema-dependent implementation, reconcile `docs/database-schema-reference.md` (currently records live head 0017) with migration `0018_distributed_rank_queue` and the actual production Alembic revision; do not assume 0018 was applied.


### 2026-10-22 implementation progress

Added `discord-bot/bf4ps_discord/overview_card.py`: standalone Pillow renderer producing 960 x 600 PNG bytes from supplied display fields and optional fancy artwork bytes. `discord-bot/requirements.txt` includes Pillow. This renderer is **not wired to the slash command** and has **not been deployed**. The existing Discord embed remains the live behavior.

The deployed manual API was inspected: it is active on TCOU at `127.0.0.1:8789`, authenticates a private token plus Origin, and delegates refresh admission to `manual_api.request_existing_soldier`. The website's manual gateway uses that loopback endpoint. A production-ready HA Discord transport and cross-collection 60-minute cooldown verification are still required. Do not expose the endpoint publicly or place the website's privileged DB credentials in the bot.

Migration `0018_distributed_rank_queue` is present in source and creates equipment ranking capacity, workers, and jobs. The schema reference's live observation remains 0017 on 2026-10-21; a direct attempt to inspect `alembic_version` with the website API's restricted DB role returned permission denied. Consequently **production revision remains unverified**; do not mark 0018 as deployed based on source presence alone.
