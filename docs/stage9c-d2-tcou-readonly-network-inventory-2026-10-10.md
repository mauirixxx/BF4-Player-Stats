# Stage 9C D2 — tcou read-only network and launcher inventory (2026-10-10)

**Scope:** read-only commands on tcou in `/opt/bf4ps-stage9c-validation`. No changes to firewall, routes, services, credentials, databases or collectors. No HTTP. Production HOLD.

## Observed

- Python grep over `bf4ps/` and `scripts/` found direct `urlopen` calls in `bf4ps/battlelog_detailed.py`, `bf4ps/battlelog_weapons.py`, `bf4ps/battlelog_vehicles.py`, and `scripts/phase5a_vehicle_payload_inspect.py`. This is **not exhaustive** for shell, dynamic imports, alternate runtimes or external programs.
- `ip -brief address`: loopback `127.0.0.1/8` and `::1/128`; `ens160` UP at `192.168.10.71/24` with IPv6 link-local address. No global IPv6 address shown.
- `ip -brief route`: default IPv4 via `192.168.10.1` on `ens160`; directly connected `192.168.10.0/24`.
- Available command paths: `/usr/sbin/ip`, `/usr/sbin/nft`, `/usr/sbin/iptables`, `/usr/bin/ss`, `/usr/bin/systemctl`. Neither `docker` nor `podman` was found via `command -v`; this does not prove no container runtime exists.
- Related unit-file names: `bf4-status-dashboard-sampler.service`, `bf4-status-dashboard.service`, `bf4ps-discovery.service`. Names do not establish their network privileges or actual process state.

## Unverified / blocked conclusions

No firewall ruleset, process socket inventory, unit contents, proxy configuration, outbound ACLs, DNS path, root bypass, IPv6 policy, or other host's routes were inspected. Nothing here proves that collectors cannot reach Battlelog directly, or that queued writes are fenced. No network changes are authorized.

## Decision

Keep **single active gateway with standby egress disabled** as the leading design candidate, not a chosen production implementation. Require independent proof of non-bypassable egress and old-sender quiescence before any failover.

Next safe inspection: read-only `nft list ruleset` / `iptables -S` with sensitive content filtered, inspect unit names and executable paths without environment secrets, and examine `ss` socket summaries. Avoid dumping environment variables or service credentials. Repeat separately on kah-01 and hnl-01 only if operator access and scope permit. Hard global 1296 ACTUAL dispatches/rolling 3600s remains unproven.
