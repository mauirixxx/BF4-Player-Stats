# Stage 9C D2 — request gate and urllib policy checkpoint (2026-10-10)

**Offline result:** 597 tests PASS on tcou, three new tests, code commit `17f447e`. No Battlelog HTTP, database mutations, or host changes. Production HOLD.

## Grounded source findings

`bf4ps/request_gate.py:33` defines `reserve_request_slot`: inserts/locks a per-egress `request_gates` row, samples `clock_timestamp()` in the row-select, computes `reserved_at=max(db_now,next_request_at)`, advances `next_request_at`, and returns a `RequestPermit` containing a future wait duration. It instructs callers to commit before HTTP. The collectors subsequently sleep, record attempt-started evidence, then call their `urllib.request.urlopen` fetch functions. This is per-egress scheduling, **not** proof of a global physical-send limit.

`scripts/bf4ps_production_collector.py` dispatches the detailed/weapons/vehicles collectors through `collect_one`. The production entrypoint is a distinct launcher, but the fetch functions remain direct HTTP origins.

Offline urllib opener inspection in `bf4ps/dispatch_urllib_policy_inspection.py` found:
- Default HTTP redirect handler present; handlers for status 301, 302, 303, 307, 308.
- On tcou's current environment, `ProxyHandler` was absent from the constructed default opener. That does not mean proxies cannot be configured elsewhere or later.

The first proxy test incorrectly assumed `ProxyHandler` must always be present. It failed on tcou; the test was corrected to reflect environment-dependent behavior, then the full suite passed. The proxy test now only checks return type and is **not a security assertion**.

## Implications

Do not equate one `urlopen` invocation with one physical HTTP dispatch: redirects may trigger another request. Automatic retries, DNS/proxy behavior and transport-level replay require explicit further inspection. A future gateway must disable or account for redirects and each possible HTTP attempt, and isolate all direct and indirect HTTP entry points.

Next safe task: write **offline mock transport tests** that demonstrate how an HTTP 302 can cause multiple request handler invocations and how a no-redirect opener behaves, without sockets. Then define the gateway transport contract. No production activation.
