# Stage 9C D2 — offline urllib redirect mock checkpoint (2026-10-10)

**Result:** 600 tests PASS on tcou, three new offline tests, code commit `0622c68`. No sockets, DNS, real HTTP, DB writes, or production changes. Production HOLD.

## Experiment

`bf4ps/dispatch_urllib_redirect_mock.py` builds a local urllib opener with an in-memory fake HTTP handler. An initial URL returns a simulated 302 Location; the target URL returns a simulated 200 JSON response. The mock counts fake handler invocations, **not physical transmissions**.

- With default redirect handler: two fake HTTP opens, initial and redirected.
- With an explicit redirect-refusing handler: one fake HTTP open; initial 302 surfaces as an HTTP error.
- The third test compares logical attempt costs between the two configurations.

Initial run failed because the synthetic response omitted the `msg` attribute required by urllib's HTTP error processor. Corrected the fake response; full suite then passed.

## Design implications

1. The future gateway transport must explicitly disable automatic redirects or reserve/count each resulting possible HTTP request separately.
2. The current direct `urlopen` fetch functions have no explicit redirect refusal, so their single call site is **not** evidence of a single physical HTTP request.
3. This mock does not prove that disabling redirects alone prevents retries, proxies, transport replays, queued writes, or bypass paths.
4. The original hard bound remains **1296 actual physical HTTP dispatches in any rolling 3600 seconds globally**. Logical handler invocations are not an acceptable substitute for physical-send accounting.

Next safe task: define a gateway HTTP-attempt contract with explicit redirect refusal, retry prohibition, unique attempt IDs and durable possible-send reservation. Keep implementation offline until transport/network enforcement assumptions are independently verified.
