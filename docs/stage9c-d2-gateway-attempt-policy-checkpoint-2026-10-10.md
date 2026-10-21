# Stage 9C D2 — gateway HTTP-attempt contract checkpoint (2026-10-10)

**Offline result:** 617 tests PASS on tcou, 17 new tests, code commit `26f6375`. No HTTP, database writes, host configuration or collector activation. Production HOLD.

Reference design: `docs/stage9c-d2-gateway-http-attempt-contract-2026-10-10.md`.
Code: `bf4ps/dispatch_gateway_attempt_policy.py`.
Tests: `tests/test_dispatch_gateway_attempt_policy.py`.

Validated: nonempty attempt IDs, supported resources/platforms, positive integer persona ID, GET-only method, explicit redirect refusal, zero automatic retries, reservation-before-handoff, duplicate reservation denial, replay denial and distinct retry identities. The registry is **in-memory, single-process, and offline**. It is not a production admission controller, durable ledger, transport wrapper, or physical-send fence.

Next: build a no-network integration model connecting the attempt policy to conservative possible-send accounting and the three-host failover model. Do not connect to real `urlopen` until network isolation, redirect/retry behavior, and physical send-boundary proof are reviewed. Hard global limit remains 1296 ACTUAL physical dispatches in any rolling 3600 seconds.
