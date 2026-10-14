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


## Batch 2 — BF4 vehicle wiki candidate matches (Battlelog verification pending)

These are Battlefield Wiki **BF4 vehicle-list names**, not yet independently verified against Battlelog. Original keys and catalog IDs are unchanged.

| Vehicle ID | Raw key suffix | Proposed name | Status |
|---:|---|---|---|
| 4 | UH1Y | UH-1Y Venom | Wiki candidate |
| 7 | AAV | AAV-7A1 AMTRAC | Wiki candidate |
| 8 | 50CAL | .50 Cal | Wiki candidate |
| 11 | TOW | M220 TOW Launcher | Wiki candidate |
| 14 | ZFB05 | ZFB-05 | Wiki candidate |
| 17 | SPM3 | SPM-3 | Wiki candidate |
| 18 | PAKFA | Su-50 | Wiki candidate |
| 20 | ZBD09 | ZBD-09 | Wiki candidate |
| 22 | Q5 | Q-5 Fantan | Wiki candidate |
| 24 | PWC | PWC | Wiki candidate |
| 25 | AC130 | AC-130 Gunship | Wiki candidate |
| 28 | CB90 | RCB-90 | Wiki candidate |
| 32 | LAVAD | LAV-AD | Wiki candidate |
| 35 | LYT2021 | LYT2021 | Wiki candidate |
| 38 | OLDCANNON | Old Cannon | Wiki candidate |
| 39 | Z9 | Z-9 Haitun | Wiki candidate |
| 42 | ACV | ACV | Wiki candidate |
| 43 | QUAD | Quad Bike | Wiki candidate |
| 44 | 9K22 | 9K22 Tunguska-M | Wiki candidate |
| 46 | LAV25 | LAV-25 | Wiki candidate |
| 49 | RIB | RHIB Boat | Wiki candidate |
| 50 | A10 | A-10 Warthog | Wiki candidate |
| 51 | DPV | Desert Patrol Vehicle | Wiki candidate |
| 52 | KA60 | KA-60 Kasatka | Wiki candidate |
| 53 | PANTSIR | Pantsir-S1 | Wiki candidate |
| 59 | CENTURION | Centurion C-RAM | Wiki candidate |
| 60 | LD2000 | LD-2000 AA | Wiki candidate |
| 61 | VDV | VDV Buggy | Wiki candidate |
| 64 | KORNET | 9M133 Kornet Launcher | Wiki candidate |
| 65 | HJ8 | HJ-8 Launcher | Wiki candidate |
| 72 | DIRTBIKE | Dirt Bike | Wiki candidate |
| 74 | PGZ95 | Type 95 AA | Wiki candidate |
| 77 | SKIDLOADER | Skid Loader | Wiki candidate |
| 78 | BTR90 | BTR-90 | Wiki candidate |

Reference: https://battlefield.fandom.com/wiki/Battlefield_4 (Vehicles of Battlefield 4).

**Note:** Several raw keys differ substantially from wiki names (e.g. `PAKFA` → `Su-50`, `CB90` → `RCB-90`); these remain candidates until Battlelog confirms the exact display wording.

## Batch 3 — remaining 13 vehicle catalog entries

**Candidate names only.** Names here are not independently confirmed as exact Battlelog strings. Ambiguous entries explicitly require manual review. Vehicle classification remains unchanged.

| Vehicle ID | Raw key suffix | Proposed name | Status |
|---:|---|---|---|
| 3 | MORTAR | M224 MORTAR | Wiki candidate; Battlelog unverified |
| 9 | MAV | MAV | Wiki candidate; Battlelog unverified |
| 10 | UCAV | UCAV | Wiki candidate; Battlelog unverified |
| 16 | BOMBER | BOMBER | Manual review needed |
| 29 | EOD | EOD BOT | Wiki candidate; Battlelog unverified |
| 31 | AAMINE | AA MINE | Wiki candidate; Battlelog unverified |
| 48 | RAWR | RAWR | Wiki candidate; Battlelog unverified |
| 57 | MKV | MKV | Manual review needed |
| 58 | SU39 | SU-39 | Wiki candidate; Battlelog unverified |
| 66 | SUAV | SUAV | Wiki candidate; Battlelog unverified |
| 70 | GROWLER | GROWLER ITV | Wiki candidate; Battlelog unverified |
| 81 | COUGAR | COUGAR | Manual review needed |
| 82 | 50CALNOSHIELD | .50 CAL (NO SHIELD) | Manual review needed |

Potential ambiguity: COUGAR may have a fuller model name; .50 CAL (NO SHIELD) may share Battlelog label with another variant; BOMBER may be a generic stat grouping; MKV may refer to a DLC pickup. Verify these directly before approving display labels.

Reference: https://battlefield.fandom.com/wiki/Category:Gadgets_of_Battlefield_4 and https://battlefield.fandom.com/wiki/Category:Vehicles_of_Battlefield_4

### Batch 3 follow-up: operator observations and MKV investigation

| Vehicle ID | Raw suffix | Proposed label | Evidence / next check |
|---:|---|---|---|
| 16 | BOMBER | BOMBER | Operator directly observed `BOMBER` in the kill feed; stats-screen label still unverified |
| 57 | MKV | RORSCH MK-1 | **Hypothesis only**, not confirmed; compare Battlelog stats against D3 MKV kills |
| 81 | COUGAR | COUGAR | Operator investigating exact label |
| 82 | 50CALNOSHIELD | .50 CAL (NO SHIELD) | Operator investigating exact label |

Read-only D3 spot check for vehicle item 57: `MeuchteFoese` (PC persona `359554335`) has **3,440** MKV kills; `Jothink` (PS4 persona `1934717859`) has **792**. These counts can be compared with their Battlelog RORSCH MK-1 statistics. Collection timestamps and exact Battlelog UI label must be checked before confirming identity.

### Batch 3 correction — MKV and BOMBER

| Vehicle ID | Key | Current conclusion | Evidence |
|---:|---|---|---|
| 57 | MKV | **Unknown — no proposed display name** | Operator rejected RORSCH MK-1 hypothesis; RORSCH MK-1 corresponds to RAILGUN |
| 16 | BOMBER | **BOMBER — operator confirmed** | Exact in-game kill-feed label; Battlelog stats-screen spelling not separately verified |

**Correction supersedes the earlier Batch 3 follow-up.** Do not use the previously suggested MKV → RORSCH MK-1 mapping. The source-of-truth CSV records the current conclusion.
