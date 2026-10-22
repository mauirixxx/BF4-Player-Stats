# `/pstats player` — initial exact-name lookup

The initial public player lookup is `/pstats player name:<exact name> platform:<PC|PlayStation|Xbox>`.

It searches the **current** soldier name only, case-insensitively, using the existing `ix_soldiers_current_name_lower` index and a platform filter. No substring search, autocomplete, historical alias search, or fuzzy matching. The verified live schema has `soldiers(current_name,platform,persona_id,last_seen_at,soldier_id)`; platform values are `pc`, `ps4`, and `xboxone`. The read-only query has a 4-second server-side statement timeout, a 4-second connect timeout, and LIMIT 2 to detect duplicate current-name matches rather than selecting an arbitrary identity.

Success displays name, platform, and persona ID; zero matches displays `Player not found`; multiple matches reports ambiguity. All player lookup results are public. Role and channel restrictions apply to ordinary users; guild owner and configured management role bypass them. Denials are private. Statistics are intentionally not displayed yet.

The bot reads `BF4PS_STATS_DSN` separately from `BOT_DATABASE_URL`. A newly created container is required to load the environment variable. Do not commit credentials. Test a known name, a missing name, and the permission restrictions in Discord after deployment.

## Detailed overview (proposed implementation)

The player command now joins the exact-name match to `detailed_stats_current` using a bounded `LEFT JOIN`. It reports rank, time played, kills, deaths, K/D, accuracy, highest streak, KPM, SPM, wins/losses, win rate, and best class (highest class score). Undefined values show an em dash rather than invented zeros. Statistics are collected snapshots, not live Battlelog reads. No weapons or vehicles are queried. This first implementation uses a native Discord embed; image-card artwork can follow separately.
