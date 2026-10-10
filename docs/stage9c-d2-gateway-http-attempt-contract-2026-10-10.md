# Stage 9C D2 — gateway HTTP-attempt contract (2026-10-10)

**DESIGN ONLY. Production HOLD.** This contract is a proposed interface for offline validation, not an authorization to dispatch HTTP or deploy a gateway.

## Safety objective

Never exceed **1296 actual physical HTTP dispatches in any rolling 3600-second window globally** across all workers, hosts, resources and egress paths. Per-egress pacing is an additional requirement, not a substitute. An application fetch operation, SQL reservation, urllib opener call, redirect, TCP connection or completed response is not automatically equivalent to one physical HTTP dispatch.

## Proposed attempt lifecycle

- `NEW`: immutable attempt identity allocated, no network capability granted.
- `RESERVED_UNCERTAIN`: global authority durably charges one *possible* physical HTTP attempt before any network handoff. The identity is globally unique and never reused, including across retries, failover and resource classes.
- `HANDOFF_UNCERTAIN`: transport may have received request bytes; do not infer successful physical transmission or non-transmission.
- `CONFIRMED_SENT`: trustworthy physical-send evidence exists; retain in rolling window using a defensible timestamp or conservative interval.
- `PROVEN_NOT_SENT`: allowed only with evidence that this attempt could not have transmitted and can never transmit in the future; a timeout, crash, process kill, SQL lease expiry, or generation change is insufficient.
- `AMBIGUOUS`: transmission cannot be ruled out; remains charged until separately proven safe. Never auto-expire based on reservation age.

State transitions must be durable and serialized with the global budget authority. Replaying an attempt ID must never generate another send.

## Request policy

1. **Single attempt, single HTTP request:** no implicit redirect following, HTTP-level automatic retry, or transparent replay. The HTTP client must be explicitly configured and verified. An HTTP 3xx is a terminal response for the current attempt; following Location requires a **new** globally charged attempt identity and separate authorization.
2. **Explicit retry:** every retry gets a new attempt ID, a new reservation, and per-egress pacing. A timeout or 5xx does not authorize a free retry.
3. **Target restrictions:** HTTPS only, allowlisted Battlelog host and known endpoint paths, explicit method GET, no arbitrary caller-supplied URL, no user-controlled proxy or redirect destination. Authentication and request validation are gateway responsibilities.
4. **No bypass:** collectors and diagnostics must not possess an alternate path to Battlelog egress. Network isolation must cover IPv4, IPv6, proxying, DNS resolution, subprocess tools, alternate runtimes and privileged configuration changes. These conditions are not yet demonstrated.
5. **Fail closed:** database authority unavailable, unknown fencing generation, unverified egress boundary, or insufficient global possible-send capacity => no new physical attempt.
6. **Audit:** persist attempt identity, resource, platform/persona reference, host, egress identity, generation, timestamps and uncertainty transitions without secrets. No assumption that an HTTP response proves exactly one physical send.

## Non-negotiable limitation

An in-process check immediately before `urlopen` cannot by itself enforce a hard physical-send limit under arbitrary pauses or queued writes. Durable possible-send accounting is conservative only if every possible physical HTTP attempt is charged exactly once before it can occur and no attempt can transmit more than once. Those are **unproven transport and network assumptions**, not guaranteed by this design document.

## Offline implementation plan

- Build a **pure policy validator** for resource/platform/persona/attempt identity and redirect/retry behavior. It must not import socket clients or issue HTTP.
- Test denial of redirects, duplicate attempt IDs, unreserved attempts, and free retries.
- Keep gateway-to-collector integration and physical egress disabled until a separate operator-reviewed network and transport proof is complete.
