# Stage 9C D2 — buffered-write failover adversarial checkpoint (2026-10-10)

**Result:** 635 tests PASS on tcou, eight new offline tests, code commit `673a80b`. No HTTP, sockets, database writes, host configuration or collector activation. Production HOLD.

Files: `bf4ps/dispatch_gateway_buffered_failover_adversarial.py`, `tests/test_dispatch_gateway_buffered_failover_adversarial.py`.

The model permits a queued old-owner write to escape after logical generation fencing, even when the coordinator refuses new old-owner sends. The old attempt remains conservatively charged against global possible-send capacity. Tests cover tcou-to-kah-01 and tcou-to-hnl-01 failover, disconnected old owner, a delayed write at 86400 seconds, duplicate attempt identity rejection, single modeled buffer flush, and refusal to flush nonexistent buffers.

**Limits:** These are synthetic logical transport emissions. The model assumes one buffered transmission maximum per attempt, does not emulate kernel TCP behavior, and does not establish whether an actual remote HTTP request occurred. The retained possible-send burden protects the modeled accounting invariant only under explicit assumptions; it is not a physical network guarantee.

**Next proof obligation:** determine how a real gateway can establish (a) no collector bypass, (b) one charged reservation per *possible* physical attempt including redirects/retries, and (c) safe handling of old queued writes across failover. Until then the 1296 actual dispatches/rolling 3600 seconds requirement is unproven and production stays HOLD.
