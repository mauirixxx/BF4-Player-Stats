# Stage 9C — outbound dispatch architecture decision record

**Status:** PROPOSED DESIGN; no implementation authorization. **Production:** HOLD. **Evidence:** offline 485/485 tests reported passing at HEAD 235a1d0; no physical-HTTP guarantee established.

## Decision context

Existing `background_service._usage` accounts for background `collection_attempt_started` events in the previous hour plus unexpired job reservations without a matching start event. `claim_production_background_job` serializes distributed admission via a PostgreSQL transaction advisory lock. `request_gate.reserve_request_slot` serializes pacing per `egress_key` via a PostgreSQL row lock, commits a future slot, and lets the caller sleep locally. The detailed, weapons, and vehicles collectors each commit a start event and then invoke HTTP outside the transaction. The three fake-fetch characterization tests prove a stale worker can reach the fetch call after simulated lease loss. They do not measure actual network dispatch.

**Desired contractual property:** no more than 1,296 actual background outbound HTTP dispatches in any rolling 60-minute window, across all participating workers. This is stricter than 1,296 recorded authorizations. Define whether redirects, transport retries, DNS retries, and connection attempts count; otherwise the property is not measurable. Do not silently substitute an authorization-count property.

## Alternatives

| Property | A: direct HTTP + bounded permit | B: independently mediated outbound dispatch |
|---|---|---|
| Reuse of current code | High | Moderate; transport call sites change |
| Additional deployment | None | Dispatcher/proxy deployment and routing |
| Egress IP preservation | Native per worker/site | Requires per-site dispatch or explicitly routed egress; central proxy changes source IP |
| Lease/owner validation | Still separate from HTTP | Can validate inside dispatch service; does not make network atomic by itself |
| Arbitrary worker pause | Still a check-to-HTTP gap | Worker pause before submission is manageable if dispatcher validates on receipt |
| Arbitrary dispatcher pause | N/A | Still a dispatch-to-socket gap; independent mediation alone is not a formal proof |
| Failure mode | Worker failure or DB outage | Dispatcher outage, queueing, split-brain, replay, and site partition |
| Strict rolling-hour guarantee | Not established | Not established without enforcing at the actual transport boundary |
| Development risk | Lower initially, unresolved strict guarantee | Higher initially, may yield better enforceability |

## Recommendation: staged Option B evaluation, not immediate deployment

1. **Freeze the requirement.** Keep the 1,296 actual-HTTP rolling-hour ceiling as the safety target. Specify which outbound attempts count and whether a strict guarantee is operationally required even under arbitrary OS suspension.
2. **Build a no-network dispatcher model** in tests, distinct from the current `dispatch_entrypoint` policy-only prototype. The model owns intake, durable admission, and a fake transport boundary; the worker supplies an idempotency key (job ID, attempt number, resource, lease token) and never calls the transport directly.
3. **Prove failure scenarios** with controlled time/barriers: stale worker submits after lease loss; duplicated submission; dispatcher restart after admission; worker retry after lost acknowledgment; hour-boundary pause; two dispatchers competing; DB unavailable; per-egress pacing. Record *actual fake transport invocations*, not merely event inserts.
4. **Define the enforcement boundary.** A dispatcher validating and then calling HTTP is subject to its own TOCTOU pause. A strict guarantee requires the accounting and send admission to be coupled to a boundary that can reject stale dispatches, with bounded timing assumptions or network-level enforcement. State the assumptions explicitly; do not claim arbitrary-pause safety without proof.
5. **Retain egress identity.** A single central outbound proxy is not acceptable by default because it collapses site-specific public egress IPs. Evaluate one dispatch authority per egress site with global PostgreSQL accounting, or a transport design that preserves the intended site IP. Global accounting must remain serialized across sites.
6. **Failure behavior:** fail closed if the dispatcher cannot confirm durable admission; do not silently fall back to direct worker HTTP. Prefer availability loss over exceeding the budget. Idempotency must prevent replay from generating a second outbound request, while acknowledging that crashes after send but before recording the result are intrinsically ambiguous without destination cooperation.
7. **Go/no-go checkpoint:** compare prototype evidence and complexity with Option A. If B cannot prove the required invariant without unacceptable infrastructure, pause and explicitly renegotiate the contract; do not quietly deploy A as if equivalent.

## Out-of-scope for this decision

No schema changes, migrations, real Battlelog traffic, service deployment, worker role changes, or production access. Do not wire the existing policy-only `dispatch_entrypoint` to real HTTP and call the strict budget solved.

## Acceptance evidence required

- Deterministic zero-HTTP tests proving correct fake dispatch counts and failure handling for all three resource types
- Documented schema checked against live scratch PostgreSQL before integration queries
- Scratch-only cross-host contention tests, controlled by the operator
- Independent review of actual HTTP accounting semantics, including redirects/retries and the pause boundary
- Explicit T4/T5 signoff; production remains HOLD until authorized
