# BF4 equipment display-name audit

Inventory from read-only D3 leaderboard API, October 2026: 170 weapon and 63 vehicle entries (233 total).

The wiki is a source of candidate names, not proof of exact Battlelog UI labels. Keep original catalog IDs and localization keys intact. Do not merge equipment statistics as part of naming.

| Vehicle ID | Raw suffix | Candidate wiki name | Status |
|---|---|---|---|
| 47 | M1ABRAMS | M1 Abrams | candidate |
| 27 | T90 | T-90A | candidate |
| 69 | T99 | Type 99 MBT | candidate |
| 45 | AH1Z | AH-1Z Viper | candidate |
| 33 | MI28 | Mi-28 Havoc | candidate |
| 37 | Z10 | Z-10W | candidate |
| 19 | F35 | F-35 | candidate |
| 40 | J20 | J-20 | candidate |
| 2 | DV15 | DV-15 Interceptor | candidate |
| 41 | Z11 | Z-11W | candidate |
| 80 | AH6 | AH-6 Little Bird | candidate |

Reference: https://battlefield.fandom.com/wiki/Category:Vehicles_of_Battlefield_4

## Authoritative catalog and review workflow

**Source of truth:** [equipment-name-inventory.csv](catalog/equipment-name-inventory.csv). This Markdown document is the **human-readable audit/report**, not a second independent mapping database.

For every review batch:

1. Read the current CSV first; identify rows by the combination of `kind` and `catalog_id`, and verify the original `raw_key`. Do not renumber entries or change the raw key to match a display label.
2. Write a readable Markdown audit table with **ID, raw key or suffix, proposed name, evidence, and status**. Group related equipment for easy review.
3. Update the corresponding CSV rows **in the same batch**: `proposed_label`, `status`, and `source`. Leave `current_label` as the existing fallback/UI label until separately deployed.
4. Use explicit states: `unreviewed`, `wiki_candidate_unverified_battlelog`, `existing_site_label_unverified_battlelog`, `battlelog_confirmed`, or `needs_manual_review`. Do **not** mark wiki-only guesses as Battlelog-confirmed.
5. Verify row count (currently 233), uniqueness of `(kind, catalog_id)`, preservation of raw identifiers, and consistency between Markdown tables and CSV before committing both files together.
6. Only after review and approval should a separate display-only website change consume confirmed CSV labels. No schema, collector, or statistic-aggregation changes.

The CSV always wins if the two documents disagree: correct the audit to reflect the verified CSV record, or update the CSV with evidence and then regenerate/correct the audit. Never silently propagate conflicting labels.

## Current progress

- **233 total entries**: 170 weapon and 63 vehicle rows.
- **11 wiki candidate vehicle names** recorded.
- **5 existing site display labels** recorded for independent Battlelog spelling checks.
- **217 unreviewed** entries.

Next: match wiki categories and subcategories, then confirm exact labels in Battlelog before website deployment.

