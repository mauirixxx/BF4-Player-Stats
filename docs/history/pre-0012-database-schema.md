# BF4PS PostgreSQL Schema Design v1

This document defines the initial PostgreSQL data model for BF4 Player Stats (BF4PS). It is the architectural contract for migration 0001. Changes to these decisions must be documented with the migration that changes them.

## Goals

- Keep BF4SW operational data separate from BF4PS-owned data.
- Use BF4SW read-only as a continuous discovery source for known soldiers.
- Make BF4 soldier identity independent of mutable player names and Battlelog profile privacy.
- Retain compact historical overall-stat snapshots.
- Keep weapon and vehicle data as replaceable current state in v1.
- Normalize static weapon/vehicle metadata into catalogs.
- Never store entire Battlelog JSON payloads as the primary data model.
- Make polling/retry state explicit rather than inferring it from gameplay data.

## Identity rules

The stable gameplay identity is the pair `(persona_id, platform)`.

BF4PS uses an internal surrogate `soldier_id bigint generated ... identity` as the relational primary key, while enforcing a unique constraint on `(persona_id, platform)`. The surrogate keeps foreign keys compact and prevents platform strings from being repeated through every statistics table.

Supported initial platform values are `pc`, `ps4`, and `xboxone`. The collector maps these to Battlelog platform integers 1, 32, and 64 respectively.

Names are mutable attributes, never primary keys.

## Tables

### soldiers

One row per BF4 persona/platform identity.

Core columns:

- `soldier_id bigint` PK;
- `persona_id bigint NOT NULL`;
- `platform text NOT NULL`;
- `current_name text NOT NULL`;
- `first_seen_at timestamptz NOT NULL`;
- `last_seen_at timestamptz NOT NULL`;
- `created_at timestamptz NOT NULL`;
- `updated_at timestamptz NOT NULL`.

Constraints/indexes:

- UNIQUE `(persona_id, platform)`;
- CHECK platform in the supported set;
- index on case-insensitive current-name lookup (for example `lower(current_name)`);
- index on `last_seen_at` for collector prioritization.

### soldier_sources

Records every independent way a soldier became known to BF4PS. Discovery provenance is many-to-one: the same soldier may be discovered manually and later observed by BF4SW without changing identity or losing either fact.

Core columns:

- `soldier_id bigint` FK -> soldiers ON DELETE CASCADE;
- `source_type text NOT NULL`;
- `first_seen_at timestamptz NOT NULL`;
- `last_seen_at timestamptz NOT NULL`.

Primary key: `(soldier_id, source_type)`. Initial source types are `bf4sw` and `manual`. Future discovery mechanisms may add source types without altering the soldier identity model.

A manual submission of an already-known BF4SW soldier adds/refreshes the `manual` provenance row rather than creating a duplicate soldier. Likewise, a manually seeded inactive soldier can later acquire a `bf4sw` source if that player returns to the game.

### soldier_names

Historical alias/name observations for a soldier.

Core columns:

- `soldier_name_id bigint` PK;
- `soldier_id bigint` FK -> soldiers ON DELETE CASCADE;
- `name text NOT NULL`;
- `first_seen_at timestamptz NOT NULL`;
- `last_seen_at timestamptz NOT NULL`.

Constraint: UNIQUE `(soldier_id, name)`.

A collector seeing a known alias again updates `last_seen_at`; a newly observed spelling/name creates a row and updates `soldiers.current_name` when that source is considered authoritative/current.

### battlelog_profiles

Optional account-level profile enrichment. A profile is not required for a soldier to exist or be collected.

Core columns:

- `profile_id bigint` PK;
- `battlelog_username text NOT NULL`;
- `battlelog_user_id bigint NULL`;
- `country_code char(2) NULL`;
- `country_name text NULL`;
- `access_state text NOT NULL`;
- `last_checked_at timestamptz NULL`;
- `last_success_at timestamptz NULL`;
- `last_error text NULL`;
- `created_at timestamptz NOT NULL`;
- `updated_at timestamptz NOT NULL`.

Initial access states: `public_country`, `public_no_country`, `friends_only`, `not_found`, and `error`.

Country code is normalized uppercase. `error` is an operational result, not evidence that country is absent.

Use a case-insensitive unique index on Battlelog username. The nullable numeric Battlelog user ID is not required for v1 operation but is available if reconnaissance/implementation can populate it reliably.

### profile_soldiers

Maps Battlelog profiles/accounts to BF4 soldiers.

Columns:

- `profile_id bigint` FK -> battlelog_profiles ON DELETE CASCADE;
- `soldier_id bigint` FK -> soldiers ON DELETE CASCADE;
- `first_seen_at timestamptz NOT NULL`;
- `last_seen_at timestamptz NOT NULL`.

Primary key: `(profile_id, soldier_id)`.

Do not impose a unique constraint on `soldier_id` in v1. We have confirmed one account can expose multiple soldiers; we have not established enough rename/account-transfer behavior to make the inverse relationship an irreversible database constraint.

### detailed_stats_current

One current normalized detailed-stat row per soldier.

Primary key/FK: `soldier_id bigint` -> soldiers ON DELETE CASCADE.

It contains the RAW fields from Detailed Stats Retention Contract v1, including rank, time played, score categories, game-mode scores, kills/deaths/assists/wins/losses/shots, team/objective counters, extra counters, and Battlelog's authoritative `quitPercentage`.

Additional metadata:

- `source_fetched_at timestamptz NOT NULL`;
- `updated_at timestamptz NOT NULL`.

Derived values such as K/D, KPM, SPM, combat SPM, and accuracy are not columns.

### detailed_stats_history

Append-only historical snapshots of the same retained RAW detailed-stat contract.

Columns:

- `snapshot_id bigint` PK;
- `soldier_id bigint` FK -> soldiers ON DELETE CASCADE;
- all RAW retained detailed-stat fields;
- `observed_at timestamptz NOT NULL`.

Indexes:

- `(soldier_id, observed_at DESC)`;
- optional BRIN on `observed_at` once table volume justifies it.

Snapshot rule: append when the supported overall state differs from the most recent stored snapshot. Do not create duplicate snapshots solely because another poll occurred. `detailed_stats_current` is updated on every successful normalized fetch; history records meaningful state observations.

The current and history tables intentionally duplicate the retained columns. Current-state queries stay cheap while history remains append-only and simple to reason about. A JSONB snapshot is deliberately rejected for v1 because these fields are known, queryable, and form an explicit contract.

### weapon_catalog

Static/reference identity for Battlelog weapons.

Core columns:

- `weapon_id bigint` PK;
- `weapon_guid text NOT NULL UNIQUE`;
- `name text NOT NULL`;
- `slug text NULL`;
- `category text NULL`;
- `first_seen_at timestamptz NOT NULL`;
- `last_seen_at timestamptz NOT NULL`.

Catalog metadata can be refreshed when Battlelog provides better values. UI image/unlock/progression blobs are not stored.

### soldier_weapon_stats

Current weapon state only.

Columns:

- `soldier_id bigint` FK;
- `weapon_id bigint` FK;
- `kills bigint NOT NULL`;
- `headshots bigint NOT NULL`;
- `shots_fired bigint NOT NULL`;
- `shots_hit bigint NOT NULL`;
- `time_equipped_seconds bigint NOT NULL`;
- `source_fetched_at timestamptz NOT NULL`;
- `updated_at timestamptz NOT NULL`.

Primary key: `(soldier_id, weapon_id)`.

KPM, accuracy, HSKR, and kills-per-hit are derived. No weapon history table exists in schema v1.

A successful complete weapon refresh is treated as authoritative current state: upsert rows present in the response and remove/zero stale player-weapon rows according to collector semantics established during implementation. A partial/failed response must never erase current state.

### vehicle_catalog

Static/reference identity for Battlelog vehicles.

Core columns mirror weapon_catalog:

- `vehicle_id bigint` PK;
- `vehicle_guid text NOT NULL UNIQUE`;
- `name text NOT NULL`;
- `slug text NULL`;
- `category text NULL`;
- first/last-seen timestamps.

### soldier_vehicle_stats

Current vehicle state only.

Columns:

- `soldier_id bigint` FK;
- `vehicle_id bigint` FK;
- `kills bigint NOT NULL`;
- `time_in_seconds bigint NOT NULL`;
- `destroy_x_in_y bigint NULL` only if implementation confirms the field is required/meaningful for supported display;
- `source_fetched_at timestamptz NOT NULL`;
- `updated_at timestamptz NOT NULL`.

Primary key: `(soldier_id, vehicle_id)`.

Vehicle KPM and formatted time are derived. No vehicle history table exists in schema v1.

### collection_state

Operational state belongs outside gameplay-stat rows.

One row per soldier. Each resource (`detailed`, `weapons`, `vehicles`, `profile`) must independently distinguish at least:

- `never_attempted`;
- `success`;
- `temporary_failure`;
- `unavailable` only when Battlelog returns a understood, meaningful unavailable result rather than an arbitrary transport/parser failure.

Per-resource bookkeeping includes:

- last result/state;
- `*_last_attempt_at`;
- `*_last_success_at`;
- `*_next_due_at`;
- consecutive failure count;
- last error class/message as needed;
- `updated_at timestamptz NOT NULL`.

Profile access semantics remain in `battlelog_profiles.access_state`; a successful request that establishes `friends_only` or `public_no_country` is still a successful collection attempt rather than an operational failure.

This separates scheduling/failure bookkeeping from the authoritative last-good statistics. A failed Battlelog request must never overwrite or invalidate the last known good stats. A successful response containing legitimate zero/empty gameplay data is also not a failure.

Indexes on the `*_next_due_at` columns support efficient collector work selection.

The exact work-queue table/schema is intentionally not frozen yet. Collection-state semantics are required for migration 0001; queue representation will be finalized after collector scheduling/claiming behavior is settled.

## Discovery and seeding

BF4PS has two first-class discovery paths in v1: continuous BF4SW discovery and explicit manual submission. Neither source owns the soldier record.

### Continuous BF4SW discovery

BF4SW is an ongoing source, not a one-time import. A BF4PS discovery job periodically queries the BF4SW database using a dedicated read-only account. Production reconnaissance established that `bf4_player_aliases` is the v1 identity-discovery contract; BF4PS does not use the much larger `bf4_player_sessions` table as its normal identity feed.

The authoritative BF4SW discovery row supplies `id`, `platform`, `persona_id`, `player_name`, `normalized_name`, `first_seen`, and `last_seen`. BF4PS upserts these observations into its own `soldiers`, `soldier_names`, and `soldier_sources` records.

Discovery is incremental and idempotent. The durable BF4PS-side discovery cursor is the monotonically increasing `bf4_player_aliases.id`. Normal polling selects rows with `id > last_bf4sw_alias_id`, ordered by `id`, in bounded batches. The cursor advances to the highest successfully processed alias ID only in the same successful BF4PS transaction as the corresponding upserts. A crash or BF4PS transaction failure therefore causes harmless reprocessing rather than silently skipped identities.

A new alias row for an already-known `(persona_id, platform)` updates/creates name provenance without creating a duplicate soldier. This naturally captures later BF4SW persona enrichment because BF4PS consumes only resolved alias rows, rather than trying to reproduce BF4SW's unresolved-session/enrichment logic.

### BF4SW platform normalization

The integration uses an explicit mapping and does not persist BF4SW's display-oriented labels as BF4PS platform identity values:

| BF4SW | BF4PS | Battlelog integer |
| --- | --- | ---: |
| `PC` | `pc` | 1 |
| `PS4/5` | `ps4` | 32 |
| `XBox` | `xboxone` | 64 |

Unknown/unmapped source platform values are an importer error and must not be guessed.

### Manual submission

Manual submission exists specifically so BF4PS can collect valid Battlelog soldiers that BF4SW has never observed, including players inactive for years.

Preferred input is a normal BF4 Battlelog soldier URL because it encodes the soldier name, persona ID, and platform. Administrative/API input may also accept an explicit name, persona ID, and platform tuple.

Before a previously unknown manual identity is accepted, BF4PS validates the persona/platform against Battlelog's lightweight detailed-statistics endpoint. A successful valid response creates/upserts the soldier, records `source_type = manual`, and requests a complete detailed/profile/weapons/vehicles collection. Invalid/unresolvable submissions do not create a normal collectable soldier record.

Submitting an identity already present from BF4SW does not duplicate it; it adds/refreshes manual provenance and may promote stale/missing resource work. Names remain mutable observations and are never identity keys.

Manual submissions are an interactive/high-priority workload class. They should be serviced as soon as technically practical after already in-flight work, subject to the same measured Battlelog safety limits as all other traffic. Manual demand must not bypass throttling or create unbounded concurrent requests.

The exact public input workflow is deferred. It must later define accepted identifiers, name/platform ambiguity resolution, validation, duplicate handling, abuse/rate limiting, and user-visible queue/ETA behavior.

## Discovery cadence, production scale, and collection separation

BF4SW discovery is continuous rather than a one-time seed operation. The initial target cadence is **every 5 minutes (300 seconds)** and must be configurable rather than hard-coded:

```text
BF4SW_DISCOVERY_INTERVAL_SECONDS=300
```

Production reconnaissance on 2026-10-02 found **178,211 alias rows / 175,730 unique persona-platform identities** before the arrival-rate sample, split across 114,290 PC, 29,324 PS4/5, and 32,116 Xbox identities. A later sample during the same reconnaissance showed `MAX(bf4_player_aliases.id) = 178449`. Recent arrival measurements showed 14 new alias rows in 5 minutes, 148 in one hour, and 2,542 in 24 hours. Daily new-alias counts over the sampled two-week period were commonly in the low thousands and reached more than 4,500 on the busiest sampled day.

The five-minute discovery interval is therefore operationally modest. Discovery consists of small indexed BF4SW reads plus local BF4PS upserts; it is not permission to immediately issue Battlelog requests for every imported identity.

**Discovery and Battlelog collection are separate queues/concepts.** BF4PS should import the complete known identity population, including the large initial BF4SW bootstrap, without generating a Battlelog request storm. Initial/backlog collection must be paced independently according to measured Battlelog capacity.

Manual submissions are explicitly user/operator requested and should be eligible for prompt high-priority collection. Recently active BF4SW identities may receive higher collection priority than old/inactive BF4SW-only identities. The large pre-existing BF4SW population is a low-priority bootstrap backlog that can be worked down safely over time.

BF4SW activity/freshness is also separate from alias-ID discovery. `bf4_player_aliases.id` answers **what identity/name observations are new to BF4PS**. Re-observation/activity information such as BF4SW `last_seen` may later be consumed by a separate mechanism to influence collection priority. Do not replace the alias-ID discovery cursor with a `last_seen` timestamp cursor: BF4SW continually updates active aliases, which would repeatedly reread large sets of already-known identities.

The five-minute value is an initial operational default, not a permanent architectural requirement. Production evidence may justify a shorter or longer interval.

## Collection policy v1

### Initial BF4SW bootstrap

The existing BF4SW identity population is a large background bootstrap workload. Initial collection priority is:

1. detailed statistics;
2. profile/country;
3. weapons;
4. vehicles.

This ordering is **priority-based, not a global phase barrier**. Lower-priority work may begin whenever capacity is available; BF4PS does not need every soldier's detailed request to finish before the first profile/weapon request can occur.

Detailed statistics are intentionally first because the endpoint is small and makes a discovered soldier broadly useful/searchable without immediately paying the much larger weapon/vehicle transfer cost. Raw large Battlelog responses are parsed into the retention contract and discarded; they are not stored simply because they were expensive to download.

### Activity-aware gameplay freshness

For a player currently/recently observed by BF4SW on monitored servers, gameplay-stat refreshes have an initial **60-minute minimum interval**. A player still active does not become eligible for another normal gameplay refresh merely because a page was viewed if the last successful refresh is less than 60 minutes old.

When BF4SW no longer observes the player, BF4PS should obtain a successful post-observation/final collection after the player's latest known BF4SW activity. If the relevant gameplay stats were successfully collected after that last-observed timestamp, the player is considered current/parked and requires no periodic gameplay refresh until new activity or an explicit high-priority request makes collection appropriate again.

BF4SW observation is deliberately described as **last observed on monitored servers**, not proof of the player's globally exact BF4 play/stop time. Website wording must preserve that distinction. Final presentation wording is deferred.

### Profile/country freshness

A successful profile/country collection has an initial refresh interval of **30 days**. This applies to stable successful outcomes such as a known country, a public profile with no country configured, or a successfully recognized restricted/friends-only profile.

Operational failures do not inherit the 30-day success interval; they use retry/backoff policy. Other terminal-looking states such as `not_found` may receive their own interval after Battlelog behavior is better characterized.

### Manual/interactive collection

A manually submitted player requests a complete collection: detailed statistics, profile/country, weapons, and vehicles. Interactive work should normally be selected ahead of background bootstrap/scheduled work once the collector finishes its current in-flight request, but it must remain subject to Battlelog rate limits and global safety controls.

Multiple users requesting the same soldier/resource must be coalesced/promoted rather than generating duplicate Battlelog traffic. A fresh resource should be served from BF4PS rather than forcing another Battlelog request solely because a page was viewed.

The website should eventually expose a best-effort estimate for when queued manual collection is expected to be attempted, especially under concurrent demand. ETA calculation and wording are deferred until measured collector throughput/rate limits exist.

### Last-good data and stats resets

Failed, throttled, malformed, or partial Battlelog responses never erase last-known-good BF4PS statistics.

A genuine Battlelog/player stats reset is different: the new lower cumulative values become the current Battlelog truth, while BF4PS preserves all pre-reset detailed-stat history and records a reset boundary/event so historical graphs and analysis can distinguish a reset from ordinary progression. The exact BF4 stats-reset semantics and reset-detection algorithm require dedicated reconnaissance before implementation; decreases in cumulative counters must not be blindly interpreted as normal gameplay.

## PostgreSQL HA requirements

BF4PS owns a separate PostgreSQL database (for example `bf4_playerstats`) while sharing the existing BF4 PostgreSQL HA infrastructure with BF4SW. Database separation is logical/operational; it does not require a separate PostgreSQL server fleet.

Because the existing BF4 PostgreSQL topology uses physical streaming replication, the BF4PS database will be replicated with the cluster when created in that cluster. BF4PS must nevertheless treat **database replication** and **client connection failover** as separate concerns.

BF4PS components that write to `bf4_playerstats` must not permanently hard-code a specific database VM such as `mak-db-01` as the writable primary. The eventual deployment must use the BF4 infrastructure's stable current-primary/failover mechanism so that a PostgreSQL promotion does not require application redesign.

BF4PS has two conceptually different database connection paths:

1. **BF4PS-owned database:** read/write access to the current writable primary for stats, discovery state, collector coordination, migrations, and manual submissions.
2. **BF4SW database:** strictly read-only access used for soldier discovery/activity observations.

The BF4SW read path may eventually be able to use a suitable replica, but replica selection, acceptable replication lag, DNS/service discovery, failover behavior, and read-after-failover semantics are deferred until the existing BF4 PostgreSQL HA client-routing design is reviewed. Do not embed an assumption in v1 that BF4SW reads always target the primary or always target a replica.

A BF4SW database outage must pause only BF4SW-origin discovery/activity updates. It must not stop the BF4PS website from serving stored data or Battlelog collectors from updating already-known soldiers.

A BF4PS database outage/failover must never cause BF4PS to write into BF4SW. The integration remains a one-way read-only boundary.

## Collector/scanner deployment direction

BF4PS should reuse the operational lessons and distributed footprint already established by BF4SW while remaining a separate application/container and workload.

The preferred architecture to evaluate is a **24/7 BF4PS background collector deployed on the same eight worker nodes that currently run BF4SW**, using its own Docker image/processes and BF4PS database coordination. The intent is to reuse existing hosts/network reachability while spreading BF4PS collection load rather than creating a single collector bottleneck. This is a deployment direction to test, not an assumption that BF4PS may consume unlimited resources on those hosts.

Distributed background collectors require database-backed coordination so that one logical unit of work is claimed by only one collector at a time, with leases/expiry so abandoned work can be recovered after process/node failure. Collectors must support graceful drain/upgrade behavior and stable worker identities. Exact work-unit granularity (per resource versus bundled player work) remains open pending further collection discussion.

### Dedicated website/manual collector lane

The website/manual-submission path should have a **dedicated interactive collector lane** that only services user-requested/manual collection work rather than consuming the normal bootstrap backlog. This may be a dedicated collector process/container on the web host or another dedicated node; physical placement remains to be tested.

The interactive lane remains queue-driven. It must not let a web request synchronously hammer Battlelog or bypass rate controls. When multiple users submit work faster than Battlelog can safely service it, requests wait in priority order/coalesce as appropriate and the website reports a best-effort estimated attempt time based on measured throughput and work already ahead of the request.

Background collectors and the interactive collector may share the same BF4PS queue/coordination database while selecting different workload classes. Interactive/manual work is normally preferred over background bootstrap work, but it must not interrupt an already in-flight Battlelog request.

### Battlelog egress and interference testing

Before production collection is allowed to scale, BF4PS must measure Battlelog throttling behavior and explicitly test whether BF4PS statistics traffic interferes with BF4SW's production server-monitoring/Keeper traffic when sharing an egress IP.

Testing should characterize at least source-IP sensitivity, endpoint/request-class sensitivity, safe sustained request rate, burst behavior, HTTP/redirect/throttle responses, and recovery/cooldown behavior. BF4SW production monitoring has priority over BF4PS enrichment traffic.

If shared-IP interference is observed, BF4PS collectors should use independent egress/static IPs. Spare static IPs are available as an architectural option. The design must therefore not assume collectors share BF4SW's egress or that all BF4PS collectors share one egress IP.

The eight-node deployment also creates an opportunity to accelerate the initial seed, but concurrency must be controlled by measured Battlelog limits rather than simply multiplying a per-process request rate by eight. Global/per-egress rate coordination may be required.

Future collector design/testing must also cover:

- total detailed/profile/weapon/vehicle request workload;
- whether endpoint classes need independent rate gates;
- collector HA/failover and duplicate-work prevention;
- retry/backoff behavior;
- prioritization using recent BF4SW activity;
- aggressive backoff/parking for inactive players;
- metrics, logs, health checks, queue depth, throughput, and backlog age;
- behavior during Battlelog, BF4SW, PostgreSQL, DNS, network, or inter-site outages;
- resource isolation so BF4PS CPU/memory/network usage cannot materially degrade BF4SW on shared nodes.

## BF4SW integration boundary

BF4PS must not add foreign keys into the BF4 Server Watcher database and must not write to BF4SW tables.

The BF4PS importer/discovery process connects to BF4SW with a read-only account and copies/updates identity observations into BF4PS-owned `soldiers`, `soldier_names`, and `soldier_sources` rows. This is an application-level integration boundary, not a cross-database relational dependency.

BF4PS remains usable if BF4SW is temporarily unavailable; existing BF4PS identities and statistics remain queryable and collectable.

## Data types and normalization

- Persona IDs use PostgreSQL `bigint`.
- Cumulative counters use `bigint` unless reconnaissance proves a signed/non-integral source semantic.
- Time counters are stored as integer seconds.
- Battlelog's `quitPercentage` uses a numeric/double-compatible type; implementation should preserve enough precision to reproduce the source display.
- Country codes are uppercase two-character values.
- All timestamps use `timestamptz` and are stored in UTC by PostgreSQL convention.
- Source nulls are normalized deliberately; collector code must not blindly cast Battlelog JSON types.

## Derived-stat rules

Do not persist deterministic presentation values when the retained raw counters reproduce them:

- K/D = kills / deaths;
- KPM = kills / (seconds / 60);
- SPM = score / (timePlayed / 60);
- combat SPM = combatScore / (timePlayed / 60);
- accuracy = shots_hit / shots_fired;
- weapon HSKR = headshots / kills;
- weapon kills-per-hit = kills / shots_hit.

Division-by-zero behavior belongs in the query/application layer and must be consistent.

## History and retention

Overall detailed-stat history is retained indefinitely in v1. The expected rows are compact enough that premature pruning/partitioning is unnecessary.

Weapon and vehicle history is intentionally absent. Their current tables can later gain corresponding history tables without changing soldier/catalog identity.

No raw 0.5 MB weapon or vehicle response blobs are retained as routine historical data.

## Migration policy

Alembic is the migration mechanism. Migration 0001 must implement this documented schema rather than inventing additional persistence ad hoc.

Every later schema migration must include a documentation update when it changes table purpose, identity semantics, retention behavior, or source mapping. Migrations should be forward-safe and should not silently discard historical data.

## Deliberately deferred decisions

The following are not required to create schema v1 or remain deliberately open pending measurement/design:

- exact Battlelog polling/rate limits and whether limits are global, per egress, or endpoint-specific;
- exact BF4SW activity-feed implementation beyond alias-ID discovery;
- final work-queue schema and work-unit granularity;
- exact bootstrap/backlog prioritization algorithm beyond the documented ordering;
- exact physical placement of the interactive/manual collector;
- manual player-submission UI/API, accepted identifiers, ambiguity handling, abuse controls, and ETA wording;
- stats-reset semantics and detection algorithm;
- whether old history eventually needs partitioning/retention limits;
- weapon/vehicle history;
- presentation prose;
- whether `destroyXinY` earns a permanent supported field;
- production web/API caching strategy;
- authentication/user-account features for the future BF4PS website.

These decisions should be made from operational evidence rather than embedded prematurely in migration 0001.
