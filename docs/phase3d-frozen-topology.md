# BF4PS Phase 3D frozen two-host topology

Status: **FROZEN implementation input**

Date: 2026-10-04 UTC

This document supplies the host/network facts required by `docs/phase3d-two-host-runbook.md`. Phase 3D implementation must use these facts rather than infer deployment or egress topology from BF4 Server Watcher.

## Selected hosts

### Honolulu — `hnl-01`

- hostname: `hnl-01`
- primary interface: `ens160`
- LAN address: `192.168.5.70/24`
- default gateway: `192.168.5.1`
- Python: `3.12.3`
- Python executable: `/usr/bin/python3`
- PostgreSQL client: `16.15`
- observed public IPv4 egress: `76.81.69.106`
- existing BF4 Server Watcher/HA directories are present under `/opt`
- no BF4 Player Stats deployment path was observed by the reconnaissance command

### Kahului — `kah-01`

- hostname: `kah-01`
- primary interface: `ens160`
- LAN address: `192.168.21.70/24`
- default gateway: `192.168.21.1`
- Python: `3.12.3`
- Python executable: `/usr/bin/python3`
- PostgreSQL client: `16.15`
- observed public IPv4 egress: `98.155.184.38`
- existing BF4 Server Watcher/HA directories are present under `/opt`
- no BF4 Player Stats deployment path was observed by the reconnaissance command

## Egress decision

The operator confirms all eight BF4 Server Watcher nodes have their own egress public IP addresses. Direct reconnaissance also observed different public IPv4 addresses for the two selected Phase 3D hosts.

Therefore `hnl-01` and `kah-01` are **independent Battlelog egress/rate-limit domains** for the Phase 3D proof and MUST use distinct BF4PS `egress_key` values.

Frozen Phase 3D keys:

- `hnl-01`: `phase3d-hnl-01`
- `kah-01`: `phase3d-kah-01`

The egress keys intentionally do not embed the public IP address. The documented mapping above records which real network domain each stable key represents.

## Frozen collector identities

Use distinct stable Phase 3D proof identities:

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

These UUIDs identify this bounded Phase 3D proof. They are not BF4 Server Watcher worker identities and must not be reused to represent unrelated collector incarnations.

## Deployment boundary

The reconnaissance showed Python 3.12 and PostgreSQL client tooling are already present, but it did not show a BF4PS checkout/virtualenv on either host.

Do not reuse or modify `/opt/bf4-serverwatcher`, `/opt/bf4-ha`, or `/opt/bf4-ha-venv` for BF4PS.

Phase 3D should deploy an isolated BF4PS checkout/runtime on each selected host after database connectivity is proven. The exact BF4PS deployment path and dependency/bootstrap procedure will be established explicitly before execution.

## Remaining prerequisites before live 3D

No Battlelog traffic is authorized yet. Before building/executing the live two-host harness, establish:

1. both hosts can reach the same `bf4_playerstats_test` PostgreSQL primary;
2. authentication from both hosts succeeds using the intended BF4PS database credentials without exposing secrets in logs/chat;
3. both report `pg_is_in_recovery() = false` against that target;
4. both see Alembic head `0003_request_gates`;
5. the BF4PS repository/virtualenv can be deployed independently on each host;
6. a read-only host-specific preflight passes from both hosts;
7. a fresh bounded mixed-platform cohort is selected and frozen only after the distributed runtime is ready.

## Safety rule

Phase 3D remains bounded. Distinct public egress IPs permit distinct request gates, but they are **not** permission to increase request rate. Initial two-host pacing remains conservative. Battlelog limit/envelope testing is a later controlled experiment after distributed correctness is proven.
