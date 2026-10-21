# Stage 9C D2 — physical network-boundary decision gate (2026-10-10)

**DESIGN REVIEW ONLY. Production HOLD.** This gate follows the 635-pass offline buffered-failover checkpoint. It is not a deployment instruction or proof of compliance.

## The actual safety property

At every real time `t`, the number of **actual physical HTTP request dispatches** in `(t-3600,t]` across `tcou`, `kah-01`, `hnl-01`, every resource, redirect, retry and egress path must be **≤1296**. Logical job counts, SQL reservations, connection counts and response counts cannot replace this metric.

## Architecture candidates

| Candidate | Benefit | Critical unsolved proof |
| --- | --- | --- |
| SQL ledger directly in each collector | Already prototyped in D2 scratch | Late sends, uncharged redirects/retries, and bypass; does not enforce physical boundary |
| Shared gateway on each host, DB generation fence | Parallel local egress | Stale queued writes after generation changes; network partition and host fencing |
| Single active egress gateway, standby kept network-inert | Simplest initial physical egress ownership | Exclusive network path, bounded attempts, safe failover when old gateway has queued writes |
| Dedicated network proxy/firewall enforcement | Can remove direct collector bypass | Policy coverage (IPv4/IPv6/proxy/DNS/privileged hosts), precise request-level accounting, HA of enforcement device |

**Recommended investigation order:** single active gateway with all collector HTTP routed through a *non-bypassable* boundary, and no automatic standby takeover until old egress is independently proven inert. A gateway process alone is not a boundary: host routing/firewall and privileged bypass must be independently audited.

## Required evidence before any real transport activation

1. **Egress inventory:** read-only enumerate all BF4PS HTTP origins, subprocess tools, container runtimes, IPv4/IPv6 paths, proxies, and host/service launchers. Current Python source inventory is useful but incomplete.
2. **Attempt semantics:** prove a reserved attempt cannot produce more than one physical HTTP request; redirects disabled; retries, proxies, HTTP client upgrades and transport-level replays explicitly addressed. Otherwise charge worst-case multiplicity, or refuse send.
3. **Durable uncertain-send authority:** one globally serialized admission and replay fence. Uncertain attempts remain charged until safe non-transmission proof; SQL timeout/lease expiry is not proof.
4. **Handoff barrier:** demonstrate old gateway can no longer transmit *including previously queued bytes* before enabling successor egress. Merely revoking a generation or killing a process is insufficient.
5. **Measurement:** capture independent per-request evidence at the enforcing network boundary. Timestamp definitions, clock uncertainty, window edges, redirects, retries and loss of telemetry must be specified. Monitoring is evidence, not the sole enforcement mechanism.
6. **Fail-closed failure matrix:** PostgreSQL primary loss/replica promotion, gateway crash, host partition, firewall reload, DNS/proxy changes, leader split-brain, kernel-buffered data, and stale clients all deny unverified new attempts.
7. **Rollout approval:** explicit operator approval for host/network changes, scratch-only dry runs, a rollback path, and a separately approved production launch. No live HTTP experiments in this stage.

## Go/no-go decision

**NO-GO** until the above evidence exists. The 635 passing offline tests establish only modeled behavior, not the real physical-send bound.

## Next safe engineering task

Add an offline **proof-obligation matrix** mapping each claim to code, tests, evidence and open gaps. Then perform read-only host networking/launcher inspection with narrowly scoped commands that do not expose credentials or change firewall/routing. The results should update this document before selecting a deployment design.
