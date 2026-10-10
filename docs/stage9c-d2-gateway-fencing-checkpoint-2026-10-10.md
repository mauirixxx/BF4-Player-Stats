# Stage 9C D2 — offline gateway fencing checkpoint (2026-10-10)

**Result:** 577 tests PASS on tcou, seven new offline tests. Code commit `958eb17`; no database mutation or HTTP. Production HOLD.

Model: `bf4ps/dispatch_gateway_fencing_model.py`; tests: `tests/test_dispatch_gateway_fencing_model.py`.

The model assumes an atomic generation check at the simulated physical-send boundary. It tests single-use handoff, replay refusal, stale-generation rejection after a simulated crash/fence, persistent uncertainty across fencing and arbitrary time, and capacity availability for a new generation only when sufficient unconsumed capacity remains.

**Crucial limitation:** The model does not implement real network-level fencing or prove that an already-running socket operation cannot transmit after the generation changes. In reality, the check-to-send gap and transport buffering can invalidate the simulated atomic check. Nor does the model prove a gateway is the only available egress path. Treat these tests as a specification of desired behavior, not evidence of a hard physical HTTP rate guarantee.

Next design investigation: determine an enforceable physical-send boundary and whether the transport/OS can provide the atomicity, bounded delay, or fail-closed uncertainty semantics required by the hard 1296 rolling-hour ceiling. Include process suspension after the simulated generation check as an adversarial case.
