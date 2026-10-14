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

### Batch 3 update: MKV identified

| Vehicle ID | Key | Name | Evidence |
|---:|---|---|---|
| 57 | MKV | **XD-1 ACCIPITER** | Operator Battlelog screenshot shows 57 kills; D3 mauirixxx (persona 236753552) MKV shows 57 kills. Independent player confirmation pending. |

This supersedes the earlier MKV unknown and rejected RORSCH guesses. Screenshot also shows EOD BOT, MAV, M224 MORTAR, SUAV, UCAV (RU), UCAV (US), AA MINE and RAWR. Faction-specific UCAV handling is not yet established.

### Batch 3 independent confirmation — XD-1 ACCIPITER

| Player | D3 MKV kills | Battlelog XD-1 ACCIPITER kills | Result |
|---|---:|---:|---|
| mauirixxx (PC) | 57 | 57 | Exact match |
| Suzems (PC) | 439 | 439 | Exact match; second player |

**Status: Battlelog-confirmed.** The second screenshot independently confirms the same name and count on another player. The earlier pending-independent status is superseded. COUGAR and 50CALNOSHIELD remain unverified.

### Operator decision — UCAV is final as implemented

| Vehicle ID | Key | Display label | Decision |
|---:|---|---|---|
| 10 | UCAV | **UCAV** | **Keep current website label and statistical behavior unchanged.** Operator explicitly approved; do not split into UCAV (RU) and UCAV (US) despite Battlelog displaying those separately. |

This decision supersedes earlier suggestions to investigate faction-specific UCAV handling for purposes of this display-name audit. Do not alter UCAV aggregation or naming unless the operator explicitly requests it.

### COUGAR naming review — MRAP candidate

| Vehicle ID | Raw key | Proposed Battlelog-readable label | Status |
|---:|---|---|---|
| 81 | `WARSAW_ID_P_VNAME_COUGAR` | **MRAP** | Operator naming and Battlefield Wiki vehicle identification agree; **player stats cross-check pending** |

The Battlefield Wiki MRAP page describes the Cougar H as the vehicle model; the operator confirms players recognize this vehicle as **MRAP**, not COUGAR. Do not change raw catalog ID or aggregation.

D3 COUGAR item 81 candidates: PC `DeVascon1957` 3,230 kills; `Sorenson44` 1,844; `maqser` 1,030. PS4 `Jag_ska_bara` 2,401. Compare the corresponding Battlelog MRAP statistics before marking `battlelog_confirmed`.

### COUGAR → MRAP: independent Battlelog confirmation

| Player | D3 COUGAR kills | Battlelog MRAP kills | Result |
|---|---:|---:|---|
| DeVascon1957 (PC) | 3,230 | 3,230 | Exact match |
| Sorenson44 (PC) | 1,844 | 1,844 | Exact match |

**Vehicle catalog ID 81: `COUGAR` → `MRAP` is Battlelog-confirmed.** Screenshots show the MRAP name and exact matching counts for two different players. This supersedes the earlier candidate-only status.

Additional names visible in Sorenson44 screenshot: `KA-60 KASATKA`, `LYT2021`, `PWC`, `QUAD BIKE`. Treat as screenshot evidence for spelling, without altering their records in this commit.

### Operator decision — hide .50 CAL NO SHIELD without deleting

| Vehicle ID | Raw suffix | D3 kills | Battlelog evidence | Decision |
|---:|---|---:|---|---|
| 82 | 50CALNOSHIELD | 541 (XPrincessaMiaX, PC) | `.50 CAL (RU)`, `(US)`, `(CN)` each 541 | **Hide from vehicle picker only; preserve API and database records** |

Implemented on WEBSITE via [PR #9](https://github.com/mauirixxx/BF4-Player-Stats/pull/9). This is a visibility policy, not a deletion or statistical merge. Faction-specific Battlelog labels remain evidence, not separate dropdown items.

## Vehicle naming sign-off — operator approved

Operator approved the **current proposed vehicle display names** for use on the website ("trust me bro"). This is an operator approval of presentation labels, **not** a claim that every vehicle spelling was independently checked against Battlelog. Keep per-row evidence statuses unchanged. Preserve UCAV exactly as implemented, BOMBER as BOMBER, and hide-only policy for vehicle ID 82. Do not alter raw IDs, kill counts or aggregation.

## Batch 4 — assault rifles and carbines (31 proposed labels)

First-pass readable naming candidates, derived from BF4 equipment conventions. **Not yet verified as exact Battlelog strings.** This table is synchronized with the CSV.

| Weapon ID | Raw suffix | Proposed Battlelog-readable name | Status |
|---:|---|---|---|
| 6 | SG553 | SG553 | Candidate; verify |
| 16 | TYPE95B1 | TYPE-95B-1 | Candidate; verify |
| 17 | CZ805 | CZ-805 | Candidate; verify |
| 18 | AK5C | AK 5C | Candidate; verify |
| 21 | G36C | G36C | Candidate; verify |
| 23 | ACR | ACW-R | Candidate; verify |
| 24 | MTAR21 | MTAR-21 | Candidate; verify |
| 25 | F2000 | F2000 | Candidate; verify |
| 39 | SCARH | SCAR-H | Candidate; verify |
| 45 | M416 | M416 | Candidate; verify |
| 54 | STEYRAUG | AUG A3 | Candidate; verify |
| 64 | AEK971 | AEK-971 | Candidate; verify |
| 66 | GALIL23 | ACE 23 | Candidate; verify |
| 70 | AKU12 | AKU-12 | Candidate; verify |
| 74 | GROZA4 | GROZA-4 | Candidate; verify |
| 84 | QBZ951 | QBZ-95-1 | Candidate; verify |
| 86 | BULLDOG | BULLDOG | Candidate; verify |
| 87 | GROZA1 | GROZA-1 | Candidate; verify |
| 95 | FAMAS | FAMAS | Candidate; verify |
| 98 | QBS09 | QBS-09 | Candidate; verify |
| 105 | GALIL53 | ACE 53 SV | Candidate; verify |
| 109 | M16A4 | M16A4 | Candidate; verify |
| 120 | M4A1 | M4 | Candidate; verify |
| 123 | GALIL52 | ACE 52 CQB | Candidate; verify |
| 133 | A91 | A-91 | Candidate; verify |
| 145 | SAR21 | SAR-21 | Candidate; verify |
| 156 | AR160 | AR160 | Candidate; verify |
| 168 | L85A2 | L85A2 | Candidate; verify |
| 170 | AK12 | AK-12 | Candidate; verify |
| 171 | GALIL21 | ACE 21 CQB | Candidate; verify |
| 173 | AN94 | AN-94 | Candidate; verify |

**Special attention:** `ACR` → `ACW-R`, `GALIL23` → `ACE 23`, `GALIL52` → `ACE 52 CQB`, `GALIL21` → `ACE 21 CQB`, `GALIL53` → `ACE 53 SV`, `STEYRAUG` → `AUG A3`, and `M4A1` → `M4` should be checked directly against Battlelog before declaring exact spelling.

## Batch 4 sign-off — operator approved

The operator approved the 31 Batch 4 weapon display-name candidates for website use. This is an approval of proposed presentation names, not independent Battlelog screenshot verification for each row. CSV per-row verification evidence remains unchanged.

## Batch 5 — PDWs, LMGs, shotguns and precision rifles (53 candidates)

Proposed BF4-readable labels; exact Battlelog spelling not independently verified. **Do not confuse operator approval with Battlelog screenshot confirmation.**

| Weapon ID | Raw suffix | Proposed label | Status |
|---:|---|---|---|
| 1 | RPK74 | RPK-74M | Candidate; review |
| 4 | M98B | M98B | Candidate; review |
| 5 | L86A1 | L86A2 | Candidate; review |
| 7 | 870 | 870 MCS | Candidate; review |
| 9 | RPK12 | RPK-12 | Candidate; review |
| 19 | SHORTY | SHORTY 12G | Candidate; review |
| 27 | UMP45 | UMP-45 | Candidate; review |
| 28 | MG4 | MG4 | Candidate; review |
| 29 | MP7 | MP7 | Candidate; review |
| 33 | DBV12 | DBV-12 | Candidate; review |
| 34 | L96A1 | L96A1 | Candidate; review |
| 35 | CBJMS | CBJ-MS | Candidate; review |
| 37 | UTAS | UTS 15 | Candidate; review |
| 38 | DAO12 | DAO-12 | Candidate; review |
| 49 | SCARHSV | SCAR-H SV | Candidate; review |
| 50 | PECHENEG | PKP PECHENEG | Candidate; review |
| 52 | M240 | M240B | Candidate; review |
| 53 | SRS | 338-RECON | Candidate; review |
| 55 | GOL | GOL MAGNUM | Candidate; review |
| 58 | UMP9 | UMP-9 | Candidate; review |
| 59 | PP2000 | PP-2000 | Candidate; review |
| 67 | LSAT | LSAT | Candidate; review |
| 68 | JNG90 | JNG-90 | Candidate; review |
| 71 | MK11 | MK11 MOD 0 | Candidate; review |
| 73 | USAS12 | USAS-12 | Candidate; review |
| 77 | SCOUTELIT | SCOUT ELITE | Candidate; review |
| 78 | QBB95 | QBB-95-1 | Candidate; review |
| 91 | SR338 | SR338 | Candidate; review |
| 94 | SV98 | SV-98 | Candidate; review |
| 96 | M40A5 | M40A5 | Candidate; review |
| 97 | SAIGA12 | SAIGA 12K | Candidate; review |
| 100 | AWS | AWS | Candidate; review |
| 104 | HAWK | HAWK 12G | Candidate; review |
| 108 | MPX | MPX | Candidate; review |
| 114 | SCORP | CZ-3A1 | Candidate; review |
| 116 | M249 | M249 | Candidate; review |
| 124 | ASVAL | AS VAL | Candidate; review |
| 125 | M60E4 | M60-E4 | Candidate; review |
| 126 | SVD12 | SVD-12 | Candidate; review |
| 128 | P90 | P90 | Candidate; review |
| 132 | JS2 | JS2 | Candidate; review |
| 135 | SKS | SKS | Candidate; review |
| 138 | TYPE88 | TYPE 88 LMG | Candidate; review |
| 146 | CSLR4 | CS-LR4 | Candidate; review |
| 147 | CS5 | CS5 | Candidate; review |
| 154 | SR2 | SR-2 | Candidate; review |
| 157 | M39 | M39 EMR | Candidate; review |
| 159 | MX4 | MX4 | Candidate; review |
| 161 | QBU88 | QBU-88 | Candidate; review |
| 163 | M200 | SRR-61 | Candidate; review |
| 165 | SPAS12 | SPAS-12 | Candidate; review |
| 166 | M1014 | M1014 | Candidate; review |
| 167 | PDR | PDW-R | Candidate; review |

**Worth checking closely:** `SCORP` → `CZ-3A1`, `M200` → `SRR-61`, `SRS` → `338-RECON`, `L86A1` → `L86A2`, `CBJMS` → `CBJ-MS`, and `PECHENEG` → `PKP PECHENEG`. These are plausible BF4 display names but are not direct Battlelog confirmations.

## Batch 5 sign-off — operator approved

Operator approved the 53 Batch 5 proposed weapon labels for website use. This is operator approval, not individual Battlelog screenshot verification. CSV evidence statuses remain unchanged.

## Batch 6 — sidearms, explosives, launchers and gadgets (54 candidates)

These are **candidate display labels**, not verified Battlelog strings. Ambiguous knives and rare pickups intentionally remain unreviewed.

| Weapon ID | Raw suffix | Proposed label | Status |
|---:|---|---|---|
| 3 | HK45C | COMPACT 45 | Candidate; review |
| 8 | RPG7 | RPG-7V2 | Candidate; review |
| 10 | RAILGUN | RORSCH MK-1 | Candidate; review |
| 11 | STARSTREAK | HVM-II | Candidate; review |
| 12 | C4 | C4 EXPLOSIVE | Candidate; review |
| 13 | V40 | V40 MINI | Candidate; review |
| 22 | TAURUS44 | .44 MAGNUM | Candidate; review |
| 26 | 40MM | M320 HE | Candidate; review |
| 31 | M136 | M136 CS | Candidate; review |
| 32 | SMK | M320 SMK | Candidate; review |
| 36 | IGLA | SA-18 IGLA | Candidate; review |
| 41 | M412REX | M412 REX | Candidate; review |
| 43 | LVG | M320 LVG | Candidate; review |
| 44 | SHG | M320 BUCK | Candidate; review |
| 46 | SRAW | SRAW | Candidate; review |
| 47 | REPAIR | REPAIR TOOL | Candidate; review |
| 56 | M82A3 | M82A3 | Candidate; review |
| 57 | CLAYMORE | M18 CLAYMORE | Candidate; review |
| 61 | P226 | P226 | Candidate; review |
| 62 | 3GL | M320 3GL | Candidate; review |
| 63 | QSZ92 | QSZ-92 | Candidate; review |
| 65 | SW40 | SW40 | Candidate; review |
| 75 | MP443 | MP443 | Candidate; review |
| 79 | M34 | M34 INCENDIARY | Candidate; review |
| 80 | DEFIB | DEFIBRILLATOR | Candidate; review |
| 81 | SHIELD | BALLISTIC SHIELD | Candidate; review |
| 83 | FLECHETTE | M26 DART | Candidate; review |
| 85 | CZ75 | CZ-75 | Candidate; review |
| 90 | SMK | XM25 SMOKE | Candidate; review |
| 92 | M15 | M15 AT MINE | Candidate; review |
| 93 | DEAGLE | DEAGLE 44 | Candidate; review |
| 99 | FRAG | M26 FRAG | Candidate; review |
| 101 | FLASH | M320 FB | Candidate; review |
| 103 | M67 | M67 FRAG | Candidate; review |
| 110 | M1911 | M1911 | Candidate; review |
| 111 | 93R | 93R | Candidate; review |
| 112 | IMPACT | RGO IMPACT | Candidate; review |
| 115 | MBTLAW | MBT LAW | Candidate; review |
| 117 | M2 | M2 SLAM | Candidate; review |
| 119 | M9 | M9 | Candidate; review |
| 121 | M32MGL | M32 MGL | Candidate; review |
| 122 | MASS | M26 MASS | Candidate; review |
| 127 | SMAW | SMAW | Candidate; review |
| 134 | XM25 | XM25 AIRBURST | Candidate; review |
| 136 | FLARE | HAND FLARE | Candidate; review |
| 137 | FLECHETTE | XM25 DART | Candidate; review |
| 143 | FN57 | FN57 | Candidate; review |
| 144 | SLUG | M26 SLUG | Candidate; review |
| 149 | GLOCK18 | G18 | Candidate; review |
| 151 | FGM148 | FGM-148 JAVELIN | Candidate; review |
| 152 | M18 | M18 SMOKE | Candidate; review |
| 155 | FIM92 | FIM-92 STINGER | Candidate; review |
| 158 | FYJS | FY-JS | Candidate; review |
| 169 | FLASHBANG | FLASHBANG | Candidate; review |

**Review carefully:** `GLOCK18` → `G18`, `40MM` → `M320 HE`, `M34` → `M34 INCENDIARY`, `M2` → `M2 SLAM`, `HK45C` → `COMPACT 45`, `STARSTREAK` → `HVM-II`, `M26_FLECHETTE` → `M26 DART`, `RAILGUN` → `RORSCH MK-1`, and `SHIELD` → `BALLISTIC SHIELD`. Exact Battlelog names and variant identities still require confirmation.

## Batch 6 sign-off — operator approved

Operator approved the 54 Batch 6 display-name candidates for website use; this is not individual Battlelog screenshot confirmation. Existing CSV verification statuses remain intact.

## Batch 7 — final 32 equipment identifiers

Battlefield Wiki provides names for BF4 knives and battle pickups, but **does not document which numbered `BPKNIFE` key maps to which knife**. Those remain unresolved, not guessed.

| Weapon ID | Raw suffix | Proposed name | Review status |
|---:|---|---|---|
| 2 | NECKKNIFE | NECK | Wiki-name candidate |
| 15 | USAS12NV | USAS-12 NV | Candidate; direct match needed |
| 30 | AMR2CQB | AMR-2 CQB | Wiki-name candidate |
| 42 | BPKNIFE5 | UNKNOWN | Unresolved index — needs evidence |
| 48 | BPKNIFE2 | UNKNOWN | Unresolved index — needs evidence |
| 51 | MACHETE | MACHETE | Wiki-name candidate |
| 60 | M60ULT | M60-ULT | Wiki-name candidate |
| 69 | BPKNIFE1 | UNKNOWN | Unresolved index — needs evidence |
| 76 | M82A3CQB | M82A3 CQB | Wiki-name candidate |
| 82 | KNIFEWEAVER | WEAVER | Wiki-name candidate |
| 88 | BAYONETT | BAYONET | Wiki-name candidate |
| 89 | BPKNIFE7 | UNKNOWN | Unresolved index — needs evidence |
| 102 | SADDLEGUN | MARE’S LEG | Candidate; direct match needed |
| 106 | SHANK | SHANK | Wiki-name candidate |
| 107 | BPKNIFE8 | UNKNOWN | Unresolved index — needs evidence |
| 113 | BPKNIFE4 | UNKNOWN | Unresolved index — needs evidence |
| 118 | UN6 | UNICA 6 | Wiki-name candidate |
| 129 | KNIFEPRECISION | PRECISION | Wiki-name candidate |
| 130 | AMR2 | AMR-2 | Wiki-name candidate |
| 131 | M82A3MID | M82A3 MID | Wiki-name candidate |
| 139 | BPKNIFE3 | UNKNOWN | Unresolved index — needs evidence |
| 140 | ULTIM | U-100 MK5 | Candidate; direct match needed |
| 141 | KNIFEBIPOD | C100 | Candidate; direct match needed |
| 142 | KNIFETANTO | TANTO | Wiki-name candidate |
| 148 | RFBTARGET | RFB | Wiki-name candidate |
| 150 | BPKNIFE6 | UNKNOWN | Unresolved index — needs evidence |
| 153 | KNIFE2142 | BJ-2 | Candidate; direct match needed |
| 160 | KNIFE14100BT | C100 | Candidate; direct match needed |
| 162 | ACB90 | ACB-90 | Wiki-name candidate |
| 164 | DIVERKNIFE | DIVE | Wiki-name candidate |
| 172 | AMR2MID | AMR-2 MID | Wiki-name candidate |
| 245 | SPYDER | PHANTOM | Candidate; direct match needed |

References: https://battlefield.fandom.com/wiki/Knife/Battlefield_4 and https://battlefield.fandom.com/wiki/Battlefield_4 and https://battlefield.fandom.com/wiki/M60/Battlefield_4.

**Do not deploy unverified BPKNIFE mappings.** Eight numbered `BPKNIFE` rows require a Battlelog profile comparison or authoritative localization lookup. Names such as PHANTOM, C100, and MARE’S LEG are candidates requiring additional ID-specific evidence.
