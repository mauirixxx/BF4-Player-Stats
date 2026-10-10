# Stage 9C D2 — offline adversarial timing checkpoint (2026-10-10)

**Result:** 563 offline tests PASS on tcou (nine new tests), commit `dae0f11`. No HTTP or database mutations.

Files:
- `bf4ps/dispatch_timing_adversarial.py`
- `tests/test_dispatch_timing_adversarial.py`

The deterministic counterexample has one admission at t=0 whose send is delayed until t=3602, and 1296 fresh admissions/sends at t=3601. Every rolling admission window respects 1296, but the rolling physical-send window at t=3602 contains 1297 attempts. The same counterexample holds at smaller capacities.

Additional tests show why TTL checking before a possible process pause cannot bound the send, and demonstrate the intentionally fail-closed accounting rule: an unresolved possible send remains charged even after its original admission ages out. The model is illustrative and not a validated production limiter. It assumes known timestamps for resolved sends and does not model all OS/network timing uncertainties.

**Next design gate:** specify a send-side enforcement boundary, network egress fencing, uncertain-send lifecycle and clock/transport assumptions; prove an invariant under arbitrary pauses before implementing real HTTP. Production HOLD remains mandatory.
