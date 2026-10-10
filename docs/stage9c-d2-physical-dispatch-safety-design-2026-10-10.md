# Stage 9C D2 — Physical HTTP dispatch safety design gate (2026-10-10)

**Status: DESIGN ONLY — production HOLD.** This document is authoritative for subsequent D2 send-side safety work until explicitly superseded. It does not authorize collector integration, real Battlelog HTTP, production migrations, or any traffic.

## Hard requirement and scope

Across all BF4 Player Statistics collector egress hosts (initially tcou, kah-01, hnl-01), the total number of **actual physical outbound HTTP dispatches** must never exceed **1296 in any rolling 3600-second interval**, globally. A dispatch is an attempted physical HTTP transmission, not a SQL row, claim, logical job, response, or completed request. Per-egress pacing is a separate constraint. A retry that physically transmits is another dispatch. Treat uncertain attempts conservatively.

## Verified D2 evidence, and its limit

The dedicated D2 PostgreSQL scratch tests at migration 0005 established:
- SQL/Python three-source accounting parity on four synthetic cases.
- Serialized one-slot admission with two independent transactions.
- Serialized full-capacity 1295-to-1296 admission using 1295 real synthetic ledger rows and two contenders.

These establish *database admission accounting*, not the timing or uniqueness of physical sends. The shared advisory transaction lock `pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))` and `clock_timestamp()` sampled **after lock acquisition** are necessary for the current ledger design but are not sufficient to constrain a later send.

## Counterexample: delayed transmission

At time T, worker A commits an admission row but pauses before physical HTTP. At T+3601s the admission is outside the rolling-hour SQL window. Other workers admit/send up to 1296 requests. A resumes and transmits: there can be 1297 physical sends in the current hour while the admission ledger never exceeded 1296 within its own time windows. Lease expiry, authorization TTL, and an immediate pre-send clock check **do not fix this**: the worker can pause *after* the check but before the socket operation.

A crash or network timeout can also leave ambiguous whether a request physically transmitted. Retrying an ambiguous attempt can cause two physical sends for one logical job.

## Safety principle: do not equate admission with send

To claim the hard limit, one of the following must be proven and tested:

**A. Bounded dispatch interval.** All send-capable code is behind an enforcement boundary with a defensible, measured and enforceable maximum time from the accounted event to actual transmission, including process pauses, host scheduling, failover, transport retries, connection reuse, queued writes, and OS/network buffering. Count each potential send against a conservatively expanded rolling window. A mere application-side timeout or short-lived permit is *not* proof of this bound.

**B. Fail-closed uncertain-send accounting.** Charge every authorized attempt as a *possible physical send* until evidence safely excludes future transmission. If an attempt can be delayed arbitrarily and its send status cannot be determined, its uncertainty cannot safely age out after an hour. Such attempts must retain protective capacity indefinitely (or until a verified resolution). This preserves safety at the cost of potentially stopping dispatch forever; a policy that simply ages uncertainty out is not a hard guarantee.

**C. Dedicated send-side enforcement authority.** Centralize actual transmission behind an egress enforcement component that owns the dispatch schedule, can prevent old workers from sending directly, accounts for every physical attempt and retry, and has a proved send-timing/uncertainty boundary. A proxy by itself is not magic: if it can pause after accounting and before sending, the same problem moves into the proxy. Network-level fencing, transport semantics, and restart behavior need explicit proof.

No choice is approved yet. A strict safety-first implementation must fail closed when assumptions cannot be established.

## Candidate direction for design investigation

Investigate a dedicated outbound dispatch service with enforced network policy denying direct Battlelog egress from ordinary collectors. Collectors submit logical requests, never transmit them. The service owns dispatch accounting, physical send attempts, retry policy, and global/per-egress limits. Design and prove its local send critical section, timing uncertainty treatment, crash recovery, and HA fencing *before* calling it compliant.

The service may be distributed across egress hosts only if the global authority, ownership fencing and fail-closed behavior remain intact under partitions. PostgreSQL coordination may provide admission serialization, but does not by itself make a remote network send atomic with a database commit.

## Required design proofs before code/activation

1. Precisely define what counts as a physical dispatch, including DNS/TLS connection failures, retransmission, redirect, HTTP-library retries and timeout ambiguity.
2. Define an enforceable send-side boundary and demonstrate ordinary workers cannot bypass it.
3. Provide an invariant relating possible physical-send timestamps to accounted capacity, valid under arbitrary process suspension, restart and network partition.
4. Prove every retry and recovery path preserves the invariant; classify ambiguous outcomes as possible sends.
5. Prove global coordination across tcou/kah-01/hnl-01 and per-egress pacing, with clock-skew handling.
6. Test adversarial pauses immediately before and after permit checks, network handoff, restart and lease expiry, plus overlapping rolling-hour windows.
7. Resolve ownership fencing, priority-class attribution/fairness and the interaction with existing three-source conservative accounting.
8. Maintain production HOLD until an explicitly reviewed proof and tests support the hard 1296 physical-dispatch ceiling.

## Immediate next step

Create an **offline, deterministic adversarial timing model** showing why permit TTL and admission-window accounting fail under arbitrary pauses; use it to evaluate candidate send-side designs before any live HTTP tests. No collector wiring or production DB work.
