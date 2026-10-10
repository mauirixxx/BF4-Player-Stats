# Stage 9C D2 — three-host failover model checkpoint (2026-10-10)

**Offline result:** 594 tests PASS on tcou, nine new tests, code commit `6f8c9f4`. No real HTTP, DB writes, host firewall changes or production activation.

Files: `bf4ps/dispatch_three_host_failover_model.py`, `tests/test_dispatch_three_host_failover_model.py`. Reference design: `docs/stage9c-d2-three-host-gateway-failover-design-2026-10-10.md`.

Scenarios include disconnected tcou refusing new reservations, successor generation activation on kah-01 or hnl-01, stale owner rejection after reconnection, retained uncertain-send burden after arbitrarily long elapsed time, remaining capacity across generations, invalid host/successor rejection, and duplicate attempt identity refusal across hosts.

**Limitation:** The model serializes all actions in one in-memory authority and assumes an ideal atomic send-boundary generation check. It does not simulate concurrent network writes, buffered sends, a real distributed lock, network fencing, actual PostgreSQL failover, transport retry semantics, or the physical-send invariant under arbitrary process suspension. Therefore it does not establish compliance with the hard 1296 actual HTTP dispatches per rolling hour.

Next safe work: formalize the authority's assumptions and seek a practical non-bypassable send-side enforcement mechanism. If physical-send timing and queued-write drain cannot be bounded/proved, uncertain sends must remain charged and liveness may be sacrificed. Production HOLD.
