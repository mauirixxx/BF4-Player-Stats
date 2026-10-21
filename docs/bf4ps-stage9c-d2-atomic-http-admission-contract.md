# Stage 9C D2: atomic physical-attempt admission contract

Status: design gate, **NOT approved for unattended HTTP**. Isolated D2 only.

## Existing execution boundary

`collect_one_detailed_job` claims and marks running in a committed
transaction, obtains a committed egress slot, sleeps, and then calls
`_record_detailed_attempt_started`. That function locks the owned job,
checks duplicate physical starts, inserts a durable
`collection_attempt_started` event, commits, then HTTP is issued.

The global claim limiter already serializes bounded claims and counts both
durable attempts and unstarted claimed/running reservations. However, it
does not enforce a **site-specific** ceiling or a three-hour deadline at the
last pre-HTTP boundary. The read-only `http_allowed` helper is NOT safe as
a concurrency limit.

## Required implementation

1. Extend the collector with an optional D2-only **pre-HTTP transaction
   hook** executed inside the same transaction that inserts the durable
   physical-start event, after the lease-owner row lock and before the
   insert. Default behavior for production and legacy tests must be unchanged.
2. The hook acquires a transaction-scoped advisory lock keyed by the fixed
   D2 soak run, locks `soak_runs` with `FOR UPDATE`, verifies state
   `running`, and compares PostgreSQL `clock_timestamp()` to
   `deadline_at`. It validates the worker hostname against the registered
   collector identity and the exact nine-soldier cohort.
3. Under that same lock, count distinct `(job_id,attempt_number)` physical
   start events after baseline 109 for **all sites** and for the caller's
   hostname. Reject before event insert if global count >=108 or site count
   >=36. Include both the current claimed/running reservation and other
   outstanding reservations when evaluating global headroom. The site check
   is authoritative at the physical-start boundary, not at claim time.
4. A rejected hook must not make HTTP. Release/requeue the owned job using
   existing lease-fenced primitives (or stop the worker with an explicit
   blocked result); never leave a misleading attempt-start event. If the
   transaction rolls back, the hook's decisions and event insertion roll
   back together.
5. The hook must not depend on a local JSON manifest, an in-memory counter,
   or worker uptime. A restarted worker must query the same PostgreSQL
   ledger and observe the same caps.
6. For the global cap, coordinate this pre-HTTP lock with existing bounded
   claim reservations or prove that global physical-start accounting alone
   is safe under all concurrent in-flight claims. The safer initial D2
   implementation is to acquire both locks in a fixed global order.
7. No new HTTP starts once the deadline is reached or state becomes
   `stopping`, even if the egress slot was reserved earlier. HTTP already
   in flight cannot be canceled reliably by this gate; a bounded timeout
   and post-run audit are required.

## Acceptance tests (all before ignition)

- Rollback-only DB tests for 35/36 and 36/36 site starts, 107/108 and
  108/108 global starts, stopped state, expired deadline, wrong hostname,
  stale lease, and duplicate attempt.
- Two independent connections racing for the final site slot: exactly one
  durable physical start and one rejection.
- Three physical workers with the same unrestricted shared queue, restart
  after a committed start, and audit for no more than 36 per hostname or
  108 total.
- No modifications to BF4SW production, and no unattended D2 soak until
  all gates pass.

## Caveat

A durable start event is a conservative *request authorization* record.
A process may crash after recording it but before making HTTP; counting
that event still consumes one budget slot, which is intentional.
