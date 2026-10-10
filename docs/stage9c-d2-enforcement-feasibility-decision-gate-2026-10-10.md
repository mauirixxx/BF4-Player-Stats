# Stage 9C D2 — enforcement feasibility review and decision gate (2026-10-10)

**Design-only feasibility review. Production HOLD.** This is an engineering assessment, not an assertion that any host is already configured this way. No production configuration, HTTP traffic, DB migration, or firewall change is authorized.

## What the offline results actually prove

The 594-test offline suite includes models for ledger admission, ambiguous attempts, logical generation fencing, queued writes, and three-host failover. Those models show *desired accounting behavior under explicit assumptions*. They do **not** prove that an operating-system socket, TLS library, process, proxy, or network device can atomically check a database generation and begin a physical transmission.

## Enforcement mechanisms: capabilities and missing proofs

| Mechanism | Useful capability | Why it is not sufficient by itself |
| --- | --- | --- |
| PostgreSQL advisory lock and durable reservation | Global serialization and audit trail | Commit and remote HTTP send are not atomic; old permits can transmit late |
| Short-lived permit or lease | Limits new authorization lifetime | Pause between last permit check and socket write defeats expiration |
| Gateway generation / leader lease | Rejects new work from stale leaders | Does not revoke writes already queued in kernel/transport |
| Process SIGTERM/SIGKILL / container stop | Stops future userspace execution after termination | Cannot alone establish whether bytes were sent before termination, buffered, or processed remotely |
| Host firewall / network ACL | Can block direct collector bypass if configured comprehensively | Does not establish precise historical physical send count or retract all already-emitted packets |
| Connection close / socket shutdown | Can prevent some future writes and release resources | A close acknowledgment does not prove the remote endpoint received no earlier request |
| Single egress gateway | Reduces concurrency and fencing complexity | Still has crash/uncertain-send and send-time accounting gap |
| Multiple egress gateways | Can improve availability and distribute pacing | Requires shared capacity and strong fencing under partitions, failover and clock uncertainty |
| Strict fail-closed possible-send reservations | Never silently forgets ambiguous attempts | May permanently consume capacity; assumes at most one possible physical attempt per reservation |
| Disabling automatic redirects/retries | Reduces unaccounted repeat transmissions | Must verify behavior across HTTP client, proxies and network paths |

## Key distinction: safety and liveness

Under arbitrary process pauses and ambiguous transport outcomes, there is no basis for automatically releasing every possible-send reservation after one hour while claiming a strict bound on physical sends. A safe design can conservatively keep unresolved capacity occupied, potentially indefinitely. Availability then depends on proving old transmission capability has been revoked and resolving ambiguous outcomes without guessing.

The offline models intentionally make this cost visible. Do not promise both uninterrupted throughput and a hard physical-send guarantee until a concrete enforcement boundary has been demonstrated.

## Decision proposal (not yet approved)

**Phase 1: single active gateway, fail-closed uncertainty.** Prefer a single gateway with exclusive network egress capability, no automatic HTTP retries/redirects, and durable possible-send reservations. Standby gateways can exist but must not send until old gateway transport capability is independently fenced and all outstanding possible sends remain accounted. This reduces the number of concurrent send authorities during initial proof.

**Phase 2: distributed egress only after proof.** Add tcou/kah-01/hnl-01 simultaneous gateway activity only after proving non-bypassable network isolation, transport attempt semantics, global serialization, clock handling, and fencing. Do not assume the existing three-host topology must imply three active senders on day one.

## Evidence needed from the actual deployment

1. Inventory the HTTP library and its default redirect, retry, connection-pool and proxy settings in the repository.
2. Inventory each candidate host's egress routing, IPv4/IPv6 paths, network namespaces and privilege boundary without changing them.
3. Identify where a request becomes an irreversible possible physical transmission (e.g. transport handoff), and define precisely whether the policy counts HTTP request initiation, first outbound byte, or remote receipt. The original requirement uses **actual HTTP dispatch**; any reinterpretation needs operator approval.
4. Define what concrete evidence can establish that an old gateway cannot send in the future; separate future fencing from past-send ambiguity.
5. Establish the conditions under which a durable possible-send can be safely resolved and which cases remain permanently uncertain.
6. Write an executable adversarial test plan for gateway restart, delayed sends, queued writes, partition, and PostgreSQL failover, without touching production.
7. Require explicit review of the hard safety guarantee before enabling any real traffic.

## Next action

Perform a **read-only repository transport inventory**: find every code path that could originate Battlelog HTTP, its retry/redirect behavior, and any bypass of the proposed gateway boundary. This should be grounded in actual source files rather than assumptions. Document exact file paths and findings, then design enforcement around the actual client stack.
