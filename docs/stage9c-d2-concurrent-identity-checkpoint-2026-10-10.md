# Stage 9C D2 — independent-connection identity race checkpoint (2026-10-10)

**Status:** PASS for PostgreSQL unique identity under two independent connections; **NOT** a global budget or actual-HTTP guarantee. Production HOLD.

## Executed by operator on tcou

```text
cd /opt/bf4ps-stage9c-validation
source /root/.config/bf4ps/stage9c-d2.env
.venv/bin/python -m scripts.phase5b_stage9c_d2_concurrent_ledger --execute
PASS: two independent connections, one committed identity, one duplicate rejected
```

- Database: dedicated `bf4ps_scratch_stage9c_d2` at revision `0005_stage9c_dispatch_ledger`; no shared T4 database migration.
- Two separate SQLAlchemy connections concurrently attempted to insert the same `(job_id, attempt_number, resource, lease_token)` with different `dispatch_id` values.
- Exactly one committed and the other encountered the expected unique constraint conflict. The harness checked one row for that identity and deletes only its own synthetic rows.
- This demonstrates **duplicate identity exclusion**, not that different identities share a serialized global budget.
- The next integration gate must verify two distinct identities competing for the final budget slot using the **existing** background advisory lock, after a fresh PostgreSQL clock sample and a reconciled usage query. It must not introduce a second unrelated lock.
- Even a serialized admission gate does **not** prove the hard 1,296 actual-HTTP dispatches per rolling hour bound; arbitrary delays between admission and physical send remain unresolved.

**Operational status:** Existing `bf4ps_scratch_stage9c_integration` stays on revision `0004` as the T4 regression baseline. No collector activation, HTTP transport, or production change authorized.
