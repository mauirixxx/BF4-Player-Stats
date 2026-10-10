# Stage 9C D2 — send-side enforcement boundary and uncertain-send lifecycle (2026-10-10)

**Status: proposed architecture; NOT approved for deployment. Production HOLD.**
This supplements `stage9c-d2-physical-dispatch-safety-design-2026-10-10.md` and the offline adversarial timing checkpoint. The 1296-per-rolling-3600-second limit applies to **physical HTTP dispatches**, not permits, DB rows, logical jobs, or successful responses.

## Proposed separation of responsibilities

**Collector:** requests a logical resource fetch, receives a result or failure. Cannot open a direct outbound connection to Battlelog or any permitted alternative route. It never owns HTTP retries or a raw send permit.

**Dispatch gateway:** the only component allowed to originate outbound BF4 stats HTTP traffic. It owns request shaping, the network transport, redirects, retries, and per-egress pacing. It must enforce a globally coordinated capacity rule for every possible physical attempt. A gateway on each egress host is permissible only with proved global fencing and safe partition behavior.

**Global accounting authority:** PostgreSQL can serialize *reservations* under the existing advisory transaction lock and preserve durable evidence. It cannot atomically commit a database row and perform an external network send. A lease or token is not proof that the corresponding physical send happened, or that a delayed send cannot still happen.

**Network boundary:** host/container firewall and routing policy must deny direct destination access by collectors and untrusted processes. Gateways must not expose an unrestricted generic proxy or permit bypass through alternate DNS/IP, IPv6, redirects, or tunnel routes. Firewall configuration and enforcement need explicit operator review; no rules are being changed by this design.

## Attempt state machine (design vocabulary, not schema authorization)

```text
logical request
  -> queued
  -> reserved_possible_send   [durably charges capacity]
  -> handed_to_transport      [physical-send timing becomes uncertain]
  -> observed_response | observed_failure | ambiguous_outcome
  -> resolved_only_if_no_future_send_is_proven
```

A durable `reserved_possible_send` record is charged **before** any possible physical transmission. Once a send-capable operation is handed to a transport, a crash, timeout, cancellation, or lost response does not prove that no physical dispatch occurred. Retries get **new** attempt identities and capacity charges. A failed connection that provably transmitted no HTTP dispatch may be resolved, but that proof must be specific to the definition of dispatch and transport implementation.

## Critical invariant to prove

At any time t, for every rolling window W=(t-3600,t], the maximum number of physical dispatches that **could** have occurred in W, consistent with all unresolved attempts and observed sends, must be <=1296.

Conservative upper bound for a decision at time t:

```text
recent_proven_physical_sends(t)
+ unresolved_possible_sends_that_could_occur_in_window(t)
+ newly_reserved_possible_sends
<= 1296
```

This is a *necessary safety-accounting pattern*, not yet a sufficient implementation proof. In particular, merely counting unresolved attempts as one forever is not enough if an unresolved transport can replay or duplicate a request: the system must prevent unbounded transport replays or conservatively account for every possible transmission. Nor is a DB reservation sufficient if a sender can bypass the accounting authority.

The model deliberately favors safety over liveness. With arbitrarily delayed or permanently ambiguous sends, the unresolved count may exhaust capacity indefinitely. No automatic timeout, lease expiry, or operator reset is allowed to silently erase that safety burden.

## Time and concurrency assumptions requiring proof

1. One attempt identity corresponds to at most one possible HTTP dispatch; redirects and automatic retries are disabled or each counted as another attempt. Validate HTTP library, connection pooling, proxy behavior, and restart paths.
2. Before a transport may physically dispatch, its possible-send capacity is durably charged and visible to every gateway. Transactions are serialized; no split-brain leadership or disconnected fallback.
3. No sender can transmit an old authorization after its uncertainty was released. A TTL check outside an atomic send boundary does not provide this.
4. Every potential transport handoff has an auditable lifecycle. Cancellation is not treated as non-send without transport-specific proof.
5. Clocks, timestamp sources, and boundary inclusivity are specified. Where send time is unknown, use a conservative interval rather than the permit timestamp.
6. The gateway fails closed on loss of the global authority; it never switches to an unaccounted local allowance.
7. Direct collector egress is actually blocked on tcou, kah-01, and hnl-01, including restart and configuration drift.
8. Per-egress pacing is separately enforced at the same physical-send boundary.
9. Priority class must be immutable at attempt creation if fairness accounting is required; the current D2 ledger does not snapshot it.

## Safety/liveness decision still required

There is a fundamental tradeoff: if the system permits arbitrarily late sends and cannot determine whether an old attempt may still transmit, the hard guarantee can require retaining that attempt's capacity indefinitely. A practical HA design therefore needs a demonstrable mechanism for **fencing old senders and terminating outstanding transport capability**, not merely expiring DB leases.

Options for subsequent evaluation:
- A single fenced gateway with enforced outbound routing, durable possible-send accounting, and strict retry control. Easier proof, reduced availability.
- Multiple gateways with globally serialized reservations plus network-level fencing and proven old-sender shutdown. Better availability, much harder proof.
- Fail-closed indefinite reservations for any unresolved attempt. Strong conservative baseline, potentially poor liveness.

**No option is approved.** Avoid assuming that a reverse proxy, HTTP timeout, or PostgreSQL advisory lock alone solves the atomicity gap.

## Offline validation matrix before any network test

- Pause immediately before/after reservation, authorization validation, and transport handoff.
- Kill/restart a gateway with an in-flight attempt; test uncertain outcome and duplicate-retry handling.
- Lose DB connectivity before/after reservation commit and while transmission is pending.
- Split gateways from each other; verify no local allowance or bypass.
- Force redirects, connection reuse, library retries, and timeout ambiguity.
- Advance the rolling window past the original admission timestamp while an old send remains possible.
- Validate that exhausting uncertainty produces zero new send authorizations.
- Exercise clock skew and exact boundary t-3600.
- Validate immutable attempt identity, egress key, priority class, and fencing generation.

## Next implementation checkpoint

Build a **pure offline state-machine model** for reservations, ambiguous handoff, replay and gateway fencing, with tests demonstrating both safety and unavoidable fail-closed behavior. No database migration, production configuration, firewall change, real HTTP, or collector activation until the model and enforcement assumptions have been reviewed.
