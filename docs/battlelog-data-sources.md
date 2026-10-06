# Battlelog Data Sources

This document records Battlelog behavior verified during initial BF4 Player Stats (BF4PS) reconnaissance. It is intended to be the source contract for collector and database design. Do not treat Battlelog's response schema as BF4PS's database schema.

## Design principles established by reconnaissance

- BF4 Server Watcher (BF4SW) is the initial source of known BF4 soldier identities.
- BF4PS should treat `(persona_id, platform)` as the minimum stable soldier identity required for Battlelog statistics requests.
- Battlelog account/profile data is optional enrichment and must never block gameplay-statistics collection.
- Store authoritative cumulative counters where practical; calculate deterministic rates/ratios for presentation rather than persisting redundant derived values.
- Do not persist Battlelog UI/presentation metadata or legacy fields merely because Battlelog returns them.
- Schema design follows source reconnaissance and retention decisions, not the reverse.

## Confirmed BF4 platform mapping

Battlelog embeds the following platform mapping in its page configuration:

| BF4PS platform | Battlelog slug | `platformInt` |
| --- | --- | ---: |
| PC | `pc` | 1 |
| PlayStation 4 | `ps4` | 32 |
| Xbox One | `xboxone` | 64 |

Battlelog also exposes legacy mappings such as Xbox 360 = 2 and PS3 = 4, but BF4PS initial scope is PC, PS4, and Xbox One.

## Confirmed structured statistics endpoints

The following endpoints were successfully requested anonymously for representative PC, PS4, and Xbox One personas:

```text
/bf4/warsawdetailedstatspopulate/{persona_id}/{platformInt}/
/bf4/warsawWeaponsPopulateStats/{persona_id}/{platformInt}/stats/
/bf4/warsawvehiclesPopulateStats/{persona_id}/{platformInt}/stats/
```

All three return structured JSON. Core statistics therefore do not require scraping rendered HTML.

Representative test soldiers:

| Platform | Soldier | Persona ID |
| --- | --- | ---: |
| PC | mauirixxx | 236753552 |
| PS4 | xSilverMystx | 303498475 |
| Xbox One | S0UL OF STEEL | 928420744 |

Observed approximate response sizes for the initial console samples were:

- detailed statistics: about 5.5-5.7 KB;
- weapon statistics: about 582-588 KB;
- vehicle statistics: about 453-454 KB.

This large difference matters for future polling strategy. Weapon and vehicle requests should not automatically be assumed to need the same refresh frequency as the small detailed-statistics request.

## Detailed statistics

The detailed response contains `personaId`, `platformInt`, `generalStats`, `mySoldier`, and `statsTemplate` in the tested payloads.

Useful cumulative/general fields observed include kills, deaths, score, rank, time played, shots, revives, repairs, resupplies, kit statistics, game-mode scores, and weapon-category kills.

The payload also contains fields that are irrelevant to BF4PS. Examples observed include Hardline-oriented names such as `sc_heist`, `sc_hostage`, `sc_hotwire`, `sc_bloodmoney`, `sc_bountyhunter`, `sc_squadheist`, `sc_turfwar`, and cash-related fields. These must not be copied blindly into the BF4PS schema.

Battlelog is also inconsistent about JSON datatypes in some statistics. Collector normalization must therefore be explicit rather than relying on source types as database types.

## Weapon statistics

The tested weapon payloads contain roughly 173-174 weapon entries depending on the player. The reason for the one-entry difference has not yet been established.

Player-specific raw fields observed include:

- weapon GUID;
- kills;
- headshots;
- shots fired;
- shots hit;
- accuracy;
- time equipped;
- score;
- deaths;
- service-star data.

Catalog/presentation material is also returned, including weapon name/slug/category, image configuration, unlock definitions, progression information, suggestions, and other Battlelog UI metadata. Much of the approximately 0.6 MB response is not appropriate for repeated historical storage.

### Weapon Retention Contract v1

Weapons are **current-state data only** in the initial BF4PS schema. The retained player-specific counters are:

- kills;
- headshots;
- shots fired;
- shots hit;
- time equipped.

Weapon GUID is the stable catalog identity. Display name, slug, and category belong in catalog/reference data rather than being duplicated in every player observation.

BF4PS does not initially retain weapon history, Battlelog accuracy, score, deaths, service-star data, unlock/progression state, suggestions, image configuration, or other presentation metadata. Historical weapon tracking may be added later only for a concrete use case.

### Derived weapon statistics

Useful display statistics can be calculated from raw counters:

```text
KPM  = kills / (time_equipped_seconds / 60)
ACC  = shots_hit / shots_fired
HSKR = headshots / kills
```

A third-party stats display examined during reconnaissance labels a value `KPH`; its observed value corresponds to kills per hit (`kills / shots_hit`), not kills per hour. BF4PS should use unambiguous labels if it ever exposes such a metric.

Rates and ratios that can be reproduced exactly from retained cumulative counters should normally be calculated for presentation rather than stored redundantly.

## Vehicle statistics

### Vehicle Retention Contract v1

The tested vehicle payloads contained 82 vehicle entries across PC, PS4, and Xbox One and were structurally consistent. Vehicles are **current-state data only** in the initial BF4PS schema.

Useful player-specific fields observed include:

- vehicle GUID;
- kills;
- time in vehicle (`timeIn`);
- `destroyXinY`;
- service-star data.

Catalog/reference fields include vehicle name, slug, and category. Battlelog also returns unlock/progression/UI structures that BF4PS does not need to snapshot repeatedly.

The most important vehicle display values can be derived from kills and time:

```text
KPM = kills / (time_in_seconds / 60)
TIME = formatted time_in_seconds
```

Battlelog groups individual vehicles into categories such as Main Battle Tank. Because individual vehicle rows include their category, BF4PS can calculate category totals from individual vehicle statistics rather than storing redundant category totals.

The initial retained player-specific vehicle state is vehicle GUID, kills, and `timeIn`. `destroyXinY` is retained only if subsequent implementation work demonstrates that it is required to reproduce a supported BF4PS display; service-star, unlock/progression, suggestion, image, and other UI metadata are excluded. BF4PS does not initially retain vehicle history.

### Live vehicle payload shape validation — 2026-10-06

A bounded zero-write inspector made exactly one anonymous request for frozen PC soldier `jdisa35w` (persona `513446234`, platformInt `1`). Battlelog returned HTTP 200 with a measured entity body of 452,007 bytes.

The response root contained `data`, `message`, and `type`. The vehicle collection is definitively `data.mainVehicleStats`, which contained exactly 82 entries. The inspected vehicle entry exposed these keys: `category`, `code`, `destroyXinY`, `guid`, `kills`, `killsDelta`, `name`, `serviceStars`, `serviceStarsProgress`, `slug`, `timeIn`, `timeInDelta`, `type`, `unlocks`, and `vehicle`.

For the first entry, Battlelog supplied non-null `guid`, `name`, `slug`, `category`, integer `kills`, integer `timeIn`, and numeric `destroyXinY` (observed as JSON `0.0`). Across the 82 entries, the inspector observed nulls in `killsDelta`, `timeInDelta`, `type`, and `vehicle`; none of those fields are part of the BF4PS retention contract. This validation establishes the exact collection container for implementation and removes the need to search arbitrary nested payload structures.


## Battlelog profile/account reconnaissance

Battlelog user profiles are available at:

```text
/bf4/user/{battlelog_username}/
```

Unlike the core statistics endpoints, profile enrichment currently relies on information present in the returned HTML.

### Country

For profiles that expose a country, Battlelog renders it directly in HTML. A representative structure is:

```html
<span class="location-information">
  <img src=".../common/flags/us.gif"
       alt="United States"
       data-tooltip="United States" />
</span>
```

This provides both a two-letter country code (from the flag filename) and a human-readable name.

Verified examples:

| Battlelog account | Country code | Country |
| --- | --- | --- |
| mauirixxx | us | United States |
| MorsecodeAUS | au | Australia |
| TrizepsTiger385 | de | Germany |
| Lucasss12343 | br | Brazil |

Country is user-supplied profile metadata and must not be treated as authoritative physical location.

A public profile with no country configured was subsequently identified (`zgr1mm`). The profile is anonymously viewable, contains a Presentation section, and does not expose a country/location value. This confirms that a missing country is a legitimate public-profile state and is distinct from profile restriction.

### Battlelog account versus BF4 soldier

Battlelog account identity and BF4 soldier/persona identity are distinct concepts.

A Battlelog profile can expose one or more BF4 soldiers. For example, reconnaissance observed one account with both:

- `TrizepsTiger385`, PC persona `318582368`;
- `TrizepsTiger`, Xbox One persona `1008642814155`.

A restricted TEAM-AJAX account exposed three BF4 soldiers:

- `TEAM-AJAX`, PC persona `1003662931478`;
- `AJAX4239`, Xbox One persona `1006883131478`;
- `champ1-shannsort`, PS4 persona `1980099105`.

Therefore a Battlelog username is not a safe BF4 soldier primary key. The conceptual relationship is one Battlelog account to zero or more BF4 soldiers/personas.

Battlelog pages also expose a Battlelog/profile user ID distinct from BF4 persona IDs. Whether BF4PS needs to persist that ID remains a schema-design question.

### Profile privacy

Anonymous requests to profiles such as `IIIParadoxonIII` and `TEAM-AJAX` returned HTTP 200 but rendered the message that the user is only sharing the profile with friends.

Even in that restricted state, the profile HTML still exposed associated BF4 soldier names, persona IDs, and platforms.

More importantly, profile privacy did not prevent anonymous access to the detailed gameplay-statistics endpoint for the associated personas. Successful anonymous detailed-statistics requests were verified for:

- `IIIParadoxonIII`, PC persona `366128672`;
- `TEAM-AJAX`, PC persona `1003662931478`;
- `AJAX4239`, Xbox One persona `1006883131478`;
- `champ1-shannsort`, PS4 persona `1980099105`.

Observed behavior therefore shows that Battlelog social/profile privacy and BF4 gameplay-statistics availability are independent.

**Collector mandate:** profile enrichment must never be a prerequisite for statistics collection. A restricted, missing, renamed, or temporarily unavailable profile must not make a known `(persona_id, platform)` soldier untrackable.

### Public profile with no country: zgr1mm

`zgr1mm` provides a useful negative country case:

- the profile is anonymously viewable;
- it does not show the friends-only restriction message;
- no country/location value is presented;
- it contains a user Presentation section;
- it exposes BF4 soldiers.

This gives BF4PS a confirmed distinction between at least:

1. country observed on a public profile;
2. public profile with no country configured;
3. profile metadata restricted to friends;
4. fetch/parsing failure (operational error, not a profile state).

## Profile/Country Retention Contract v1

Profile data is optional enrichment and never gates statistics collection. BF4PS retains the Battlelog username used for profile lookup, nullable two-letter country code, nullable country name, a profile access/result state, and timestamps for the last profile check and last successful profile enrichment.

The profile state must distinguish at minimum: public profile with country, public profile with no country configured, profile restricted to friends, and operational fetch/parser failure. An absent country must therefore never be represented in a way that makes it indistinguishable from a restricted profile or failed request.

Country is self-selected Battlelog metadata, not verified geolocation. Country code should be normalized to uppercase for storage/querying while preserving the Battlelog country name as observed. This supports future country-based player discovery without repeatedly scraping profiles.

The account-to-soldier relationship is one Battlelog account/profile to zero or more BF4 soldiers. Soldier identity remains `(persona_id, platform)` and must not depend on Battlelog username. BF4PS should preserve current soldier display names separately from account identity so that a profile rename cannot change the soldier's primary identity.

The numeric Battlelog profile user ID is not required by any confirmed collector endpoint or requested display feature. It is therefore not mandatory in schema v1; the schema may provide a nullable field if implementation evidence shows it can be captured reliably at negligible cost.

Presentation/profile prose is explicitly excluded from initial collection and storage.

## Retention philosophy

Battlelog is the source, not the BF4PS database model.

BF4PS should preferentially retain compact, authoritative cumulative counters and stable catalog identities. It should avoid repeated storage of:

- unlock definitions;
- image configuration;
- suggestion structures;
- Battlelog rendering metadata;
- legacy/non-BF4 statistics;
- deterministic ratios/rates that can be calculated from retained counters.

Static weapon/vehicle metadata should be normalized into catalog/reference data instead of duplicated for every player snapshot.


## Detailed Stats Retention Contract v1

This section defines the BF4 detailed-statistics values BF4PS intends to support. The mapping is based on the captured representative Battlelog payloads and the detailed-statistics presentation selected as the BF4PS baseline. Source field names below are the observed Battlelog names; earlier guessed names are intentionally not used.

### Multiplayer score

| BF4PS display | Battlelog source | Retention |
| --- | --- | --- |
| Assault Score | `assault` | RAW |
| Engineer Score | `engineer` | RAW |
| Support Score | `support` | RAW |
| Recon Score | `recon` | RAW |
| Commander Score | `commander` | RAW |
| Squad Score | `sc_squad` | RAW |
| Vehicle Score | `sc_vehicle` | RAW |
| Award Score | `sc_award` | RAW |
| Unlock Score | `sc_unlock` | RAW |
| Total Score | `score` | RAW |
| Score/Min | `score / (timePlayed / 60)` | DERIVED |
| Combat Score | `combatScore` | RAW |
| Combat Score/Min | `combatScore / (timePlayed / 60)` | DERIVED |

### Game modes

Battlelog exposes friendly top-level fields for the supported game modes. BF4PS therefore does not need the duplicate numeric-keyed `gameModesScore` object for this display contract.

| BF4PS display | Battlelog source | Retention |
| --- | --- | --- |
| Conquest | `conquest` | RAW |
| Rush | `rush` | RAW |
| Deathmatch | `teamdeathmatch` | RAW |
| Domination | `domination` | RAW |
| Obliteration | `obliteration` | RAW |
| Defuse | `elimination` | RAW |
| Capture the Flag | `capturetheflag` | RAW |
| Air Superiority | `airsuperiority` | RAW |
| Carrier Assault | `carrierassault` | RAW |
| Chain Link | `chainlink` | RAW |

Gun Master is intentionally excluded from the retained contract. Live validation against multiple players known to play Gun Master, including a Gun Master server owner known to have multiple round wins, showed Battlelog still returning `generalStats.gunmaster = 0`. BF4PS therefore treats the field as unmaintained/non-authoritative and does not store or infer a Gun Master score from another source.

### General

| BF4PS display | Battlelog source | Retention |
| --- | --- | --- |
| Kills | `kills` | RAW |
| Deaths | `deaths` | RAW |
| Kill Assists | `killAssists` | RAW |
| K/D Ratio | `kills / deaths` | DERIVED |
| Kills/Min | `kills / (timePlayed / 60)` | DERIVED |
| Wins | `numWins` | RAW |
| Losses | `numLosses` | RAW |
| Shots Fired | `shotsFired` | RAW |
| Shots Hit | `shotsHit` | RAW |
| Accuracy | `shotsHit / shotsFired` | DERIVED |

`timePlayed` is RAW and mandatory even when not shown in this particular presentation section. It is required for KPM/SPM calculations and is useful directly.

### Team and objectives

| BF4PS display | Battlelog source | Retention |
| --- | --- | --- |
| Repairs | `repairs` | RAW |
| Revives | `revives` | RAW |
| Heals | `heals` | RAW |
| Resupplies | `resupplies` | RAW |
| Avenger Kills | `avengerKills` | RAW |
| Savior Kills | `saviorKills` | RAW |
| Suppression Assists | `suppressionAssists` | RAW |
| Quits | `quitPercentage` | RAW |
| Flags Captured | `flagCaptures` | RAW |
| Flags Defended | `flagDefend` | RAW |

Although quit percentage is conceptually derived, Battlelog directly supplies `quitPercentage`. Until the exact authoritative source counters/definition for a quit are established, BF4PS retains Battlelog's supplied value.

### Extra

| BF4PS display | Battlelog source | Retention |
| --- | --- | --- |
| Dogtags Taken | `dogtagsTaken` | RAW |
| Vehicles Destroyed | `vehiclesDestroyed` | RAW |
| Vehicle Damage | `vehicleDamage` | RAW |
| Headshots | `headshots` | RAW |
| Longest Headshot | `longestHeadshot` | RAW |
| Highest Kill Streak | `killStreakBonus` | RAW |
| Nemesis Kills | `nemesisKills` | RAW |
| Highest Nemesis Streak | `nemesisStreak` | RAW |

`rank` is also RAW and retained even though it is not part of the selected detailed-statistics panel.

### Historical retention rule

BF4PS will retain history for the overall detailed-statistics state. Historical snapshots should contain the RAW fields in this contract, allowing progression and interval calculations without storing redundant ratios. A new historical snapshot is needed only when the supported overall state meaningfully changes.

Examples of values calculated from snapshots include lifetime and interval K/D, KPM, SPM, accuracy, playtime gained, score gained, revives gained, and other counter deltas.

Weapons and vehicles are initially **current-state data only**. BF4PS does not require historical weapon/vehicle snapshots in the initial schema. This can be added later if a concrete use case justifies the storage and collection cost.

### Duplicate and excluded source structures

The captured payload demonstrates duplicate representations. For example, named kit-score fields correspond to entries in `kitScores`, and named game-mode fields correspond to the numeric-keyed `gameModesScore` structure. BF4PS should retain the explicit named fields required by this contract and not duplicate those nested structures merely because Battlelog returns them.

Hardline/legacy fields such as cash statistics and `sc_heist`, `sc_hostage`, `sc_hotwire`, `sc_bloodmoney`, `sc_bountyhunter`, `sc_squadheist`, and `sc_turfwar` are explicitly outside the BF4PS retention contract.

### Live validation: 48-field contract and schema migration

On 2026-10-03, the live detailed-statistics validation for PC persona `236753552` (`mauirixxx`) returned 191 `generalStats` source fields. The explicit BF4PS normalizer retained 48 fields; all 48 were present and non-null. `gunmaster` was not retained.

The follow-up Alembic migration `0002_drop_gun_master_score` was exercised against `bf4_playerstats_test` through the complete round trip:

1. `0001_initial_schema` -> `0002_drop_gun_master_score`: both obsolete `gun_master_score` columns were absent after upgrade.
2. `0002_drop_gun_master_score` -> `0001_initial_schema`: both columns were restored after downgrade.
3. `0001_initial_schema` -> `0002_drop_gun_master_score`: both columns were absent again in the final head state.

The destination was confirmed as writable (`pg_is_in_recovery() = false`) during validation. The test database was intentionally left at `0002_drop_gun_master_score (head)`.

## Known unknowns

The following remain intentionally unresolved and must not be converted into assumptions:

- Whether friends-only is Battlelog's default profile-sharing setting.
- Why one tested Xbox One weapon response contained 173 weapon entries while PC/PS4 samples contained 174.
- Final polling cadence for detailed versus weapon versus vehicle statistics.
- Whether Battlelog profile user IDs need to be persisted.
- How account/soldier renames should be represented historically.
- Final behavior for deleted/nonexistent Battlelog profiles.
- Rate limits/throttling characteristics of these endpoints at production collection scale.
- Final PostgreSQL schema. The schema must be documented in-repository alongside the implementation, including table purpose, keys, relationships, retention/history behavior, and migration rationale.

## Current reconnaissance conclusion

Battlelog provides structured anonymous JSON endpoints for the core BF4 gameplay statistics needed by BF4PS across PC, PS4, and Xbox One. Profile HTML provides optional account-level enrichment such as self-selected country and account-to-soldier relationships. Profile privacy does not, based on tested examples, prevent gameplay-statistics collection.

This is sufficient to proceed to explicit retention decisions and evidence-based schema design without HTML scraping for core gameplay statistics.
