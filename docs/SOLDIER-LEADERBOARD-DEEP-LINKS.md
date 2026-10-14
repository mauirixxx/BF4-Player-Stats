# Soldier dossier → leaderboard deep links

## Contract

A soldier dossier equipment row links to `/index.html?metric=weapon|vehicle&item=<catalog ID>&platform=<soldier platform>&soldier=<persona ID>#leaderboards`. The exported top-equipment snapshot contains the actual catalog ID, not a guessed ID from a display name. The leaderboard uses the existing read-only SQL rank computation, which preserves global ranks and ties; searching by persona ID only filters the displayed rows, not the ranked population. Vehicle family canonicalization remains in the API.

Game-mode score rows link to the same leaderboard with `metric=<documented detailed_stats_current game-mode score column>`, platform, and persona ID. They rank exclusively on the selected mode score using the already collected detailed-stat snapshot; they do not incorporate kills or total score. No Gun Master leaderboard is added. Uncollected scores are not linked.

The page must initialize controls from validated URL parameters and retain the existing interactive platform, category, search, division, and pagination controls. Unknown parameters fall back to ordinary defaults. Links remain normal anchor tags for keyboard access and sharing. No production database migration or collector changes are required.

## Verification

Test actual soldier IDs and equipment IDs against the live API. Confirm SQL global rank stays unchanged when persona search is applied, that duplicate UCAV variants resolve to the same canonical family, and that game-mode score ordering uses the selected field only. Validate browser JavaScript syntax and public endpoints before deployment.
