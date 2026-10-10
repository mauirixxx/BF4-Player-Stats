# Stage 9C D2 — read-only repository HTTP transport inventory (2026-10-10)

**Evidence source:** read-only source inspection on tcou, branch `fix/stage9c-t4-inspector-lease-expiry`, after fast-forward to `1dbc3fd`. No HTTP executed, no DB writes or host changes. This is a scoped Python source search, **not** a comprehensive network egress audit.

## Confirmed direct HTTP origins

| Source | Transport | Invoker |
| --- | --- | --- |
| `bf4ps/battlelog_detailed.py:146` | `urllib.request.urlopen(request, timeout=timeout_seconds)` | `bf4ps/detailed_collector.py:301` |
| `bf4ps/battlelog_weapons.py:92` | same | `bf4ps/weapon_collector.py:294` |
| `bf4ps/battlelog_vehicles.py:83` | same | `bf4ps/vehicle_collector.py:294` |
| `scripts/phase5a_vehicle_payload_inspect.py:68` | direct `urlopen(request, timeout=30.0)` | standalone diagnostic script |

Additional scripts call the fetch functions (examples: `scripts/phase1_live_detailed_fetch.py`, `scripts/phase5a_vehicle_normalization_probe.py`, `scripts/phase3e_lifecycle_a_normalization_probe.py`). These may originate HTTP if executed, even when they contain no direct `urlopen` call.

All three library fetch functions build a `urllib.request.Request` with `method='GET'` and target `https://battlelog.battlefield.com`. They accept timeouts (detailed default 15s, weapon and vehicle default 30s), catch HTTP and transport errors, and parse JSON. No explicit custom redirect handler, retry policy, or proxy isolation was observed in these three fetch functions. **Absence of explicit configuration is not proof that redirects, proxies or retries are disabled**; Python urllib defaults and runtime environment require separate verification.

## Existing check-to-send gap

The three collectors reserve an egress slot via `reserve_request_slot(...)` in a DB transaction, then potentially `sleep(permit.wait_seconds)`, record attempt-started evidence, and finally call the respective fetch function:
- `bf4ps/detailed_collector.py` approximately lines 282–301.
- `bf4ps/weapon_collector.py` approximately lines 277–294.
- `bf4ps/vehicle_collector.py` approximately lines 277–294.

Thus the current transport can begin after DB reservation, a sleep, and separate evidence recording. This matches the previously modeled admission-to-physical-send uncertainty. The current code must **not** be represented as enforcing the global 1296 physical-send limit.

## Inventory scope and follow-ups

The read-only search found four direct `urlopen` call sites in `bf4ps/` and `scripts/`. It searched Python code for urllib, http clients and common direct network calls; it did not inspect all shell scripts, systemd units, containers, dynamic imports, executable tools, OS proxy settings, runtime process privileges, IPv6, DNS, or firewall/routing state. Do not claim the four sites are an exhaustive host-wide egress inventory.

Next read-only work: inspect `reserve_request_slot` and the production launcher control paths; test urllib redirect/proxy behavior using **offline mocks only**; catalog direct and indirect entry points and configuration before proposing a non-bypassable gateway. No real Battlelog HTTP.
