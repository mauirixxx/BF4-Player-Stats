# Gun Master Score Retention Decision

## Decision

BF4PS does **not** retain a Gun Master score in the Detailed Stats Retention Contract v1.

The Battlelog detailed-statistics payload exposes a `generalStats.gunmaster` field, but live validation shows that the field is not a usable authoritative BF4 statistic. It remains `0` for players known to have played and won Gun Master rounds.

This was checked against two known Gun Master players, including a Gun Master server owner known to have multiple wins. Both Battlelog detailed-statistics responses still reported `gunmaster = 0`.

Because Battlelog is the sole authoritative source for BF4PS gameplay statistics, BF4PS will not manufacture, infer, or retain a Gun Master score from another source. Presence of a source field is not sufficient reason to persist it when live evidence shows that Battlelog does not populate it meaningfully.

## Contract amendment

This decision supersedes the `Gun Master | gunmaster | RAW` row in `docs/battlelog-data-sources.md` until that broader reconnaissance document is revised. Gun Master is excluded from the retained detailed-statistics dataset.

After this exclusion, the Detailed Stats Retention Contract v1 contains **48 retained raw fields**: 46 integer fields and 2 decimal fields.

The Phase 1 normalizer intentionally ignores `generalStats.gunmaster`, even when Battlelog includes it in the response.

If future evidence demonstrates that Battlelog begins returning a meaningful Gun Master score, reintroducing it requires a new explicit retention decision and validation against known players before schema/persistence support is added.
