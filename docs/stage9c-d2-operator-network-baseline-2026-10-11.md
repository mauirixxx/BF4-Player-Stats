# Stage 9C D2 — operator-reported network baseline (2026-10-11)

**Status: operator statement plus limited read-only observations; NOT an independently verified network-policy audit. Production HOLD.**

## Operator-reported design

- Host firewalls on BF4 Server Watcher nodes and `tcou` are expected to be disabled.
- Outbound policy is handled at the perimeter firewall and, as described, concerns **egress public-IP address handling only**; it is not an HTTP request-admission policy.
- IPv6 is intentionally unused anywhere in the infrastructure by design.
- No BF4PS-specific network-level enforcement of a rolling-hour HTTP dispatch budget has been asserted.

These are operator-reported architecture facts/expectations, **not verified effective policy**. In particular, 'should be disabled' must not be upgraded to a claim that all host filtering is disabled.

## Limited read-only observations

| Host | IPv4 default route | IPv6 default route | nft tables listed |
| --- | --- | --- | --- |
| tcou | 192.168.10.1 via ens160 | none | none |
| kah-01 | 192.168.21.1 via ens160 | none | ip nat, ip filter, ip6 nat, ip6 filter, ip raw |
| hnl-01 | 192.168.5.1 via ens160 | none | ip nat, ip filter, ip6 nat, ip6 filter, ip raw |

Presence or absence of nftables tables alone does not prove effective host firewall policy. No active probe or network change was made.

## Implications for P01/P02

- Treat IPv6 as **unsupported by design**, but verify effective disabled state and absence of alternative routes before making a non-bypassability proof.
- Distinguish **egress IP steering** from **per-process outbound authorization** and **per-HTTP-attempt rate enforcement**. Public-IP steering alone does not satisfy P02 or the 1296 physical-send rolling-hour invariant.
- Do not assume the operator wants host firewalls enabled. Prefer investigating existing perimeter capabilities and whether gateway-only egress can be enforced there without disrupting BF4SW, tcou or other workloads.
- A single active gateway remains a candidate, not a selected or approved deployment. If the perimeter cannot distinguish gateway from collector traffic (e.g. same source IP without separate network identity), evaluate isolated gateway identity/VM or other enforceable segmentation, with operator approval.
- Continue read-only configuration inventory. No firewall rules, live HTTP tests, migrations or production activation without explicit approval.
