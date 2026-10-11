# Stage 9C D2 — physical HTTP dispatch proof-obligation matrix (2026-10-11)

**DESIGN / EVIDENCE INDEX ONLY. Production HOLD. No live HTTP, firewall modifications, or migrations authorized.**

## Safety claim and interpretation

For every real time `t`, actual physical HTTP request dispatches across all BF4PS collectors, gateways, redirects, retries, proxies and egress paths in the rolling interval `(t-3600,t]` must be at most **1296**. This is an **actual-send** constraint, not a cap on job claims, reservations, responses, or logical fetches. Safety must survive network partitions, stale senders, process restarts and PostgreSQL failover. If proof is unavailable, deny new sends.

The 2026-10-11 two-hour synthetic soak passed (eight workers, three sites, 97,533 balanced claim/release cycles, zero lease losses and HTTP), but is **not** evidence of this physical-send bound.

## Evidence and remaining proof obligations

| ID | Proof obligation | Existing source / evidence | Missing evidence and next test | Status |
| --- | --- | --- | --- | --- |
| P01 | Every HTTP origin and indirect launcher is inventoried | `stage9c-d2-http-transport-inventory-2026-10-10.md`: four direct urllib call sites and collector entry points | Read-only inspect systemd, cron, containers, subprocesses, env proxies, DNS, IPv4/IPv6, alternate routes and privileges on each host; reconcile complete invocation graph | OPEN |
| P02 | No collector or diagnostic process can bypass enforced gateway | `stage9c-d2-physical-network-boundary-decision-gate-2026-10-10.md` | Design network-level default-deny boundary; demonstrate policy covers alternate routes and privileged bypass; independently verify fail-closed behavior | OPEN |
| P03 | One durable admission represents at most one possible physical request | `stage9c-d2-send-boundary-uncertainty-design-2026-10-10.md`; urllib policy/offline redirect tests | Specify exact HTTP stack and disable or individually charge retries, redirects, transport replays, proxy retries, and connection reuse edge cases | OPEN |
| P04 | Global admission serializes all possible physical sends under hard 1296 rolling-window bound | `stage9c-d2-postgres-ledger-checkpoint-2026-10-10.md` and SQL/model parity checkpoints | Prove real transport cannot send late or after admission expiry; account uncertain sends conservatively; test exact window boundaries and concurrent authorities | OPEN |
| P05 | Ambiguous or delayed sends retain capacity until proven inert | `stage9c-d2-send-boundary-uncertainty-design-2026-10-10.md` | Model-check durable lifecycle through timeout, DB crash, retry, restart, arbitrarily delayed send; never release on TTL alone | OPEN |
| P06 | Failover cannot leave old gateway able to transmit | `stage9c-d2-three-host-gateway-failover-design-2026-10-10.md` | Define independent physical handoff barrier covering paused processes, kernel buffers, queued bytes, open sockets and restart paths; adversarial fault-injection proof | OPEN |
| P07 | All gateway generations use one authority and fail closed on split brain | Three-host failover model checkpoint and proposed generation fencing | Exercise partition, primary promotion, ambiguous commit, old-leader resumption and simultaneous gateways without local fallback | OPEN |
| P08 | Independent network-boundary telemetry measures physical attempts accurately | Physical network-boundary decision gate | Define dispatch event, timestamp and clock-error envelope, telemetry loss handling, packet/HTTP semantics and independent cross-host reconciliation | OPEN |
| P09 | Resource/priority/egress metadata and per-egress pacing cannot drift after reservation | `stage9c-d2-send-boundary-uncertainty-design-2026-10-10.md` notes missing immutable priority snapshot | Define schema and validation against documented migrations; adversarial tests for priority mutation, retry lane changes and egress switching | OPEN |
| P10 | Host configuration and deployment are controlled and reversible | Three-site scratch-only rehearsal and soak evidence | Read-only baseline audit, least-privilege operator review, explicit rollout approval, rollback/fail-closed plan, staged tests without production traffic | OPEN |

## Why the SQL-only approach is insufficient

Current collectors reserve slots, may sleep, record evidence, then call `urllib.request.urlopen` separately. A durable reservation and later physical transmission are not atomic. A send delayed across the rolling-hour boundary can violate the actual-send cap even if every SQL reservation was valid. A SQL generation change cannot retract kernel-buffered bytes or revoke a paused process's network capability. A gateway process without a non-bypassable network boundary cannot close this gap.

## Candidate decision (not authorization)

Investigate **one active outbound gateway with standby network-inert**, globally durable possible-send accounting, disabled/charged transport retries, and independently enforced collector egress denial. Do not activate standby until old-sender transmission capability is demonstrably fenced; otherwise preserve unresolved attempts and remain fail-closed. This simplifies the proof compared with three concurrently sending gateways but does not itself prove correctness.

## Evidence acceptance criteria

1. Each obligation P01–P10 has a named implementation location, repeatable adversarial test, independent evidence artifact, explicit assumptions and operator signoff.
2. The transport-boundary test counts actual requests, including redirects/retries, rather than merely successful responses or SQL ledger rows.
3. Tests include exact rolling-window edges, arbitrarily delayed sends, ambiguous DB commits, split brain, failover with queued bytes, telemetry loss and IPv4/IPv6 bypass attempts.
4. Any unverified safety assumption results in **zero new physical dispatch authorizations**.
5. A separate approval gate is required before any live HTTP, network policy change or production activation.

## Next bounded task

Read-only host inventory on `tcou`, `kah-01`, `hnl-01` using credential-redacted commands. Record launcher/service units, HTTP origins, proxy settings without values, IPv4/IPv6 route existence, firewall policy identity and privilege boundaries. **Do not change network settings**. Reconcile the inventory against P01/P02, then propose offline bypass tests before deployment decisions.
