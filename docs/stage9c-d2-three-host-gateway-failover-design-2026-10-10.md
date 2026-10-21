# Stage 9C D2 — three-host gateway shutdown and failover protocol (2026-10-10)

**DESIGN ONLY — NOT DEPLOYMENT APPROVAL.** Production HOLD. No HTTP, firewall changes, migrations, or collector integration authorized. Applies to the proposed gateway architecture across tcou, kah-01, hnl-01; those hosts are *candidates*, not activated gateways.

## Current evidence

D2 scratch validated database admission at capacity 1296. Offline models demonstrated delayed-send admission-window violation, ambiguous-send capacity retention, generation fencing under *ideal atomic send-boundary assumptions*, and counterexamples to check-then-send and queued-write fencing. None proves a physical network enforcement boundary.

## Proposed failover contract

1. **Request ingress:** collectors submit logical fetch requests to an authenticated gateway API; direct Battlelog egress must eventually be denied by independently verified network policy. Logical requests must not contain a transferable raw HTTP send permit.
2. **Durable reservation:** before a gateway can begin a physical HTTP attempt, the globally serialized authority charges one *possible physical send* under a unique immutable attempt identity, egress key, priority class and fencing generation. Every retry, redirect, and separate possible transmission needs its own charge.
3. **Transport ownership:** only an authorized gateway may possess the network capability to transmit. Generation changes in SQL do not revoke existing kernel buffers, established sockets, or a paused process. The actual fencing mechanism must be independently proved.
4. **Drain request:** stop admitting new work for the retiring gateway. Persist its in-flight and ambiguous attempt inventory. Never mark those attempts unsent based only on process exit, lease expiry, or a timeout.
5. **Quiescence:** require a transport-specific proof that the retiring gateway can no longer initiate or complete an outstanding transmission, including queued writes and restart paths. If this proof is unavailable, leave attempts unresolved and charged; no forced release.
6. **Successor activation:** a new gateway generation may accept work only after global authority availability and its own egress policy are confirmed. It must not reuse the retired gateway's attempt identities. Unresolved previous-generation attempts remain charged globally. If the proof of old-sender fencing is missing, the successor must not rely on fencing to reclaim capacity.
7. **Recovery:** reconcile confirmed attempts and ambiguity using durable evidence. An HTTP response can support that a request happened, but does not by itself prove the number of underlying physical attempts when automatic retries or redirects exist. A request timeout is ambiguous.
8. **Fail closed:** DB partition, loss of fencing certainty, unverified direct-egress policy, or missing attempt accounting disables new transmissions. Never fall back to a per-host 1296 allowance.

## Topology-specific fault cases

| Fault | Required conservative behavior |
| --- | --- |
| tcou gateway process crash | No new send from tcou until ownership/fencing and outstanding transport uncertainty are handled; other hosts retain old possible-send burden |
| kah-01 disconnected from global DB | kah-01 cannot issue new dispatches; existing queued writes remain uncertain |
| hnl-01 old leader resumes after failover | Old generation cannot obtain new authority; outstanding buffered writes remain charged, and physical old-sender fencing still needs proof |
| Two gateways claim leadership | Global authority must serialize generation and reject stale writers; cannot rely on SQL generation check alone for actual sockets |
| PostgreSQL failover / ambiguous commit | Treat uncertain reservation as possibly committed and possibly transmitted; no resend without distinct capacity charge |
| Host reboot during request | Preserve durable possible-send identity; reboot alone does not prove remote endpoint saw no request |
| Rolling hour advances during outage | Unresolved sends do not expire merely because their admission timestamps age out |
| Clock skew across hosts | Centralize accounting clock and use conservative physical-send timing intervals; no host-local timestamp may silently release burden |

## Required gate before live implementation

- Specify and verify the actual network egress isolation and who can modify/bypass it.
- Determine whether any supported transport can prove cancellation/drain of an in-flight or queued send. If not, document the deliberate indefinite fail-closed capacity cost.
- Specify HTTP client's retry, redirect, timeout, connection-pool, DNS and proxy behavior.
- Decide how gateway restarts preserve durable attempt identities and never repeat the same attempt.
- Define global authority HA behavior on PostgreSQL primary transition, including split-brain and uncertain commits.
- Provide a model-checkable invariant and adversarial schedule tests covering two active gateways and a recovering old gateway.
- Document operator-visible uncertainty inventory and **explicit** resolution evidence requirements; never offer a manual button that simply resets the limiter.

**Next safe work:** offline three-host failover state machine with partition/crash/queued-write scenarios and conservative burden. This document is the design reference for that model.
