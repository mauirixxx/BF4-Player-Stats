# Stage 9C D2 — offline gateway coordinator integration checkpoint (2026-10-10)

**Result:** 627 tests PASS on tcou, 10 new tests, code commit `8601d0c`. No real HTTP, database writes, host firewall changes, migrations or collector activation. Production HOLD.

New files: `bf4ps/dispatch_gateway_coordinator_offline.py` and `tests/test_dispatch_gateway_coordinator_offline.py`. This composes the existing pure gateway attempt validator and three-host possible-send/failover authority.

Coverage: validation-before-reservation; rejection of automatic redirects and retries; immutable request details bound to attempt ID; reservation-before-handoff; duplicate identity denial even after simulated send; retention of ambiguous old-generation capacity after tcou-to-kah-01 failover; stale old-owner rejection on reconnect; successor use of remaining capacity on hnl-01; no free retry when global possible-send budget is full; failed reservation does not claim a new identity.

**Strict limitations:** The coordinator is in-memory and single-process. Its `transmit` method confirms a simulated event under an idealized atomic fence; it does not invoke `urlopen`, prove actual physical-send timing, account for kernel-buffered bytes, implement durable PostgreSQL transactions, or demonstrate non-bypassable network egress. The hard 1296 actual physical HTTP dispatches per rolling 3600 seconds globally is not yet proven in any live transport. Existing scratch D2 SQL admission tests remain separate.

Next safe work: design an offline fault-injection schedule combining buffered writes, leadership handoff and request-policy enforcement. Define which safety properties rely on the unproven at-most-one-send-per-attempt assumption. Do not activate production.
