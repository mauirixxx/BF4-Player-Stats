# BF4PS Collector Registry and Identity

This document records the durable identity and current-health model for BF4PS collectors. It complements `docs/collector-architecture.md` and the eventual migration `0001` schema.

## Identity model: UUID plus human-readable name

BF4PS uses **both** a durable UUID and a human-readable collector name. They serve different purposes and must not be conflated.

- `collector_uuid` is the permanent database identity and primary key.
- `collector_name` is the unique human-readable operational name, such as `mak-01`, `hnl-02`, or `web-interactive-01`.
- `hostname` identifies the host/VM on which the collector is running and is intentionally separate from `collector_name` even when they currently match.
- `egress_key` identifies the Battlelog rate-limit/egress domain used by the collector.
- `lane` identifies the collector workload lane, initially `background` or `interactive`.

Conceptually:

```text
collector_uuid   = 9d73c4e7-3b2e-4fc5-9c73-8b8c4e9a3d21
collector_name   = mak-01
hostname         = mak-01
lane             = background
egress_key       = mak-01-public
```

Database foreign keys and lease ownership use `collector_uuid`. Operator-facing status, logs, dashboards, and troubleshooting normally display `collector_name`.

## Persistent identity

`collector_uuid` is persistent across normal operational events. It must **not** be regenerated merely because a container restarts, the host reboots, or BF4PS is upgraded.

A collector installation/bootstrap therefore receives a stable UUID and human-readable name through persistent configuration/registration. Normal lifecycle events preserve that UUID.

A deliberately replaced/re-registered collector receives a new UUID even if the replacement reuses the same human-readable name. This preserves historical truth across hardware/VM/container replacement.

Example:

```text
old collector incarnation
  collector_uuid = aaaaaaaa-....
  collector_name = mak-03
  retired_at     = 2027-04-12

replacement incarnation
  collector_uuid = bbbbbbbb-....
  collector_name = mak-03
  registered_at  = 2027-04-12
```

Historical events therefore continue to identify the exact collector incarnation that generated them.

## Collector name versus hostname

Do not assume one collector per host forever. `collector_name` and `hostname` remain separate fields even when the initial deployment uses identical values.

This allows future arrangements such as:

```text
collector_name = mak-01-bg
hostname       = mak-01
lane           = background

collector_name = mak-01-other
hostname       = mak-01
lane           = background
```

or a dedicated interactive collector such as:

```text
collector_name = web-interactive-01
hostname       = bf4ps-web-01
lane           = interactive
```

## Current collector registry / health state

BF4PS should maintain a current-state collector registry rather than attempting to derive current health solely from append-only collection events.

The conceptual `collectors` table includes fields such as:

- `collector_uuid UUID PRIMARY KEY`;
- `collector_name TEXT` (human-readable and unique among current registrations);
- `hostname TEXT`;
- `lane`;
- `egress_key`;
- `enabled`;
- `drained`;
- `registered_at`;
- `started_at` / current process start time where useful;
- `last_heartbeat_at`;
- current heartbeat/health state;
- `heartbeat_lost_at` when currently unavailable;
- BF4PS software version/build;
- `current_job_id` when applicable;
- retirement/replacement metadata as needed.

Exact SQL types, constraints, and indexes will be frozen with migration `0001`.

The current-state table should make operator queries straightforward, for example:

```text
mak-01   healthy       last heartbeat 8 sec ago
mak-02   healthy       last heartbeat 4 sec ago
mak-03   unavailable   since 2026-10-12 03:14:22 UTC
hnl-01   drained       operator requested
```

## Health history and observed downtime

Routine successful heartbeats update current collector state without generating an append-only event every time.

Meaningful health transitions are logged in `collection_events`:

- first healthy -> failed/missed transition: `heartbeat_lost`;
- repeated failures while already unavailable: no duplicate event spam;
- first subsequent successful heartbeat: `heartbeat_restored`;
- subsequent normal successful heartbeats: no event spam.

The interval between `heartbeat_lost` and `heartbeat_restored` is the collector's **observed unavailability/downtime interval** from BF4PS's perspective and is useful for troubleshooting and fleet reporting.

It is not necessarily proof that the physical/virtual host itself was powered off for that entire interval. Database, VPN, network, process, or egress failures may also prevent heartbeats. Exact host uptime/downtime, if required, remains an infrastructure-monitoring concern.

## Event snapshots

`collection_events` should reference the durable `collector_uuid` and may additionally snapshot the human-readable collector name at event time, for example:

```text
collector_uuid
collector_name_snapshot
```

This preserves readable historical presentation even if a collector is later renamed or retired, while the UUID preserves referential identity.

Persona/platform snapshots in collector events follow the same general principle: durable relational identity plus useful historical/operator context.

## Job ownership

`collection_jobs` lease ownership references `collector_uuid`, not the display name. A unique per-claim `lease_token` remains required independently of collector identity.

Thus:

```text
collector_uuid
    = which registered collector incarnation owns the claim

lease_token
    = which specific claim attempt currently owns the job
```

Both must be validated as appropriate during state-changing finalization so a stale/zombie process cannot commit work after its claim has been superseded.

## Egress identity

`egress_key` is operationally significant because Battlelog rate limiting is treated as egress-IP based. Collector identity and egress identity are therefore separate concepts.

Multiple collectors may share one `egress_key`; if so, they must share that egress rate budget. A new collector process does not create additional Battlelog capacity merely by having a different UUID or name.

The exact representation of egress IP/key and shared rate-gate state remains part of implementation design, but the collector registry must expose enough information to correlate collector failures/403s/throttling with egress identity.

## Locked decisions

The following are architectural decisions for migration/design purposes:

```text
DATABASE IDENTITY
    = collector_uuid (UUID, durable primary identity)

OPERATOR IDENTITY
    = collector_name (human-readable name)

HOST IDENTITY
    = hostname (separate from collector name)

RATE-LIMIT IDENTITY
    = egress_key (separate from collector/host identity)

WORKLOAD ROLE
    = lane (background / interactive initially)

NORMAL RESTART / UPGRADE / REBOOT
    = preserve collector_uuid

DELIBERATE REPLACEMENT / RE-REGISTRATION
    = new collector_uuid; name may be reused

JOB FOREIGN KEY / LEASE OWNER
    = collector_uuid

SPECIFIC CLAIM OWNERSHIP
    = lease_token

CURRENT HEALTH
    = collectors registry/current-state fields

HISTORICAL HEALTH
    = append-only transition events
```

These decisions should be reflected in the exact `collectors`, `collection_jobs`, and `collection_events` SQL schema before migration `0001` is finalized.
