# BF4PS Phase 3D frozen three-host topology

Status: **FROZEN implementation input — amended before live execution**

Date: 2026-10-04 UTC

This document supplies the host/network facts required by `docs/phase3d-two-host-runbook.md`. The original two-host topology was deliberately expanded before live execution to include `tcou`, giving Phase 3D three independent BF4PS processes competing for one PostgreSQL work queue.

## Selected hosts

### Makawao/control host — `tcou`

- hostname: `tcou`
- LAN address: `192.168.10.71`
- observed public IPv4 egress: `72.253.18.166`
- BF4PS checkout: `/var/www/bf4playerstats.com`
- database route to `192.168.10.78` is direct on `ens160`
- public egress is shared with BF4 Server Watcher host `mak-01`

### Honolulu — `hnl-01`

- hostname: `hnl-01`
- primary interface: `ens160`
- LAN address: `192.168.5.70/24`
- default gateway: `192.168.5.1`
- Python: `3.12.3`
- Python executable: `/usr/bin/python3`
- PostgreSQL client: `16.15`
- observed public IPv4 egress: `76.81.69.106`
- isolated BF4PS checkout: `/opt/bf4-player-stats`

### Kahului — `kah-01`

- hostname: `kah-01`
- primary interface: `ens160`
- LAN address: `192.168.21.70/24`
- default gateway: `192.168.21.1`
- Python: `3.12.3`
- Python executable: `/usr/bin/python3`
- PostgreSQL client: `16.15`
- observed public IPv4 egress: `98.155.184.38`
- isolated BF4PS checkout: `/opt/bf4-player-stats`

## Database target and naming policy

All Phase 3D hosts use the same BF4PS test PostgreSQL primary:

- FQDN: `mak-db-02.bf4statusbot.com`
- observed IPv4: `192.168.10.78`
- database: `bf4_playerstats_test`
- expected Alembic head: `0003_request_gates`

Use the FQDN in BF4PS database configuration. Do not depend on short-name DNS resolution; reconnaissance showed `mak-db-02` did not resolve from Honolulu or Kahului while `mak-db-02.bf4statusbot.com` did.

## Egress decision

The three BF4PS hosts have three observed public IPv4 egress addresses and therefore use three distinct BF4PS request gates:

- `tcou` -> `72.253.18.166` -> `phase3d-tcou`
- `hnl-01` -> `76.81.69.106` -> `phase3d-hnl-01`
- `kah-01` -> `98.155.184.38` -> `phase3d-kah-01`

The keys model real Battlelog rate-limit domains and intentionally do not embed the public IP address.

### Shared BF4SW egress caveat

`tcou` shares public egress `72.253.18.166` with BF4 Server Watcher host `mak-01`. The BF4PS `request_gates` table coordinates BF4PS requests only; it cannot pace independent BF4SW traffic. Any 403/429/throttle evidence observed on the `tcou` egress must therefore be preserved and interpreted with this coexistence in mind. Phase 3D does not intentionally increase request rate to probe that interaction.

## Frozen collector identities

- `tcou`
  - collector name: `phase3d-tcou`
  - collector UUID: `b2b3ef60-62e8-4d4a-91b0-41a2e2a3d003`
  - lane: `background`
  - egress key: `phase3d-tcou`

- `hnl-01`
  - collector name: `phase3d-hnl-01`
  - collector UUID: `b2b3ef60-62e8-4d4a-91b0-41a2e2a3d001`
  - lane: `background`
  - egress key: `phase3d-hnl-01`

- `kah-01`
  - collector name: `phase3d-kah-01`
  - collector UUID: `b2b3ef60-62e8-4d4a-91b0-41a2e2a3d002`
  - lane: `background`
  - egress key: `phase3d-kah-01`

These UUIDs identify this bounded Phase 3D proof. They are not BF4 Server Watcher worker identities.

## Frozen workload boundary

The first three-host live run is expanded from the original 12-job proposal to **36 fresh soldiers**:

- 12 PC
- 12 PS4
- 12 Xbox One
- resource: `detailed`
- lane: `background`
- hard global collection-attempt/job ceiling: **36 across all three hosts combined**

All three collectors compete for the same PostgreSQL queue. The cohort is not statically partitioned by host or platform.

Thirty-six jobs are intended to provide repeated claim/finalize cycles and sustained overlap across all three physical processes while remaining a bounded correctness test. This is not Battlelog throughput/envelope testing.

## Required three-host evidence

The normal live run must show:

1. all three frozen collector identities register distinctly;
2. all three collectors claim and successfully finalize at least one frozen-cohort job;
3. no work outside the frozen cohort is attempted;
4. no duplicate simultaneous ownership occurs;
5. the combined global boundary never exceeds 36 attempts/jobs;
6. all three real egress domains have matching request-gate state;
7. throttle/403/429 evidence is explicitly reported and reconciled;
8. final job/event/state evidence accounts for the bounded run.

Phase 3D additionally retains the previously designed lifecycle/recovery exercises: drain/stop one physical host while survivors continue, then deliberately exercise expired-work reclamation and stale-owner fencing across hosts.

## Deployment boundary

Do not reuse or modify `/opt/bf4-serverwatcher`, `/opt/bf4-ha`, or `/opt/bf4-ha-venv` for BF4PS. Honolulu and Kahului use isolated `/opt/bf4-player-stats` checkouts. `tcou` uses its existing `/var/www/bf4playerstats.com` development checkout for this bounded proof.

## Safety rule

Phase 3D remains bounded. Three public egress IPs permit three distinct request gates, but they are **not** permission to increase request rate. Initial three-host pacing remains conservative. Battlelog limit/envelope testing and deliberate BF4PS/BF4SW shared-egress testing are later controlled experiments after distributed correctness is proven.
