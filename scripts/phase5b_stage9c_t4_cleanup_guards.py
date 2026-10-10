"""Read-only referential guards for T4 cleanup; no mutations."""
from sqlalchemy import text

def refuse_foreign_references(conn, marker, rows, owners):
    names = {"marker": marker, "tcou": marker+"_tcou",
             "hnl": marker+"_hnl-01", "kah": marker+"_kah-01"}
    foreign_events = conn.execute(text("""
        SELECT COUNT(*) FROM collection_events e
        WHERE (e.job_id IN (SELECT job_id FROM collection_jobs WHERE reason=:marker)
           OR e.soldier_id IN (SELECT soldier_id FROM collection_jobs WHERE reason=:marker)
           OR e.collector_uuid IN (SELECT collector_uuid FROM collectors
               WHERE collector_name IN (:tcou,:hnl,:kah)))
          AND e.metadata->>'stage9c_t4_marker' IS DISTINCT FROM :marker
    """), names).scalar_one()
    if foreign_events:
        raise RuntimeError(f"REFUSING {foreign_events} unmarked fixture-linked events")
    owner_ids = {o.collector_uuid for o in owners}
    if any(j.collector_uuid is not None and j.collector_uuid not in owner_ids for j in rows):
        raise RuntimeError("REFUSING job owned by foreign collector")
    foreign_jobs = conn.execute(text("""
        SELECT COUNT(*) FROM collection_jobs
        WHERE soldier_id IN (SELECT soldier_id FROM collection_jobs WHERE reason=:marker)
          AND reason IS DISTINCT FROM :marker
    """), {"marker":marker}).scalar_one()
    if foreign_jobs:
        raise RuntimeError(f"REFUSING {foreign_jobs} unrelated jobs on fixture soldiers")
    # Marked events must not point at non-fixture identities; deletion is otherwise unsafe.
    foreign_marked = conn.execute(text("""
        SELECT COUNT(*) FROM collection_events e
        WHERE e.metadata->>'stage9c_t4_marker'=:marker
          AND (e.job_id IS NOT NULL AND NOT EXISTS (
                   SELECT 1 FROM collection_jobs j WHERE j.job_id=e.job_id AND j.reason=:marker)
            OR e.soldier_id IS NOT NULL AND NOT EXISTS (
                   SELECT 1 FROM collection_jobs j WHERE j.soldier_id=e.soldier_id AND j.reason=:marker)
            OR e.collector_uuid IS NOT NULL AND NOT EXISTS (
                   SELECT 1 FROM collectors c WHERE c.collector_uuid=e.collector_uuid
                   AND c.collector_name IN (:tcou,:hnl,:kah)))
    """), names).scalar_one()
    if foreign_marked:
        raise RuntimeError(f"REFUSING {foreign_marked} marked events linked to foreign identities")
