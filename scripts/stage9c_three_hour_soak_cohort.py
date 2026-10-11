"""Revision-0006 D2 cohort validation independent of legacy 0005 ignition guard."""
from sqlalchemy import text
from scripts.stage9c_three_site_live_ignition import COHORT, NODES, RUN, UUIDS
from scripts.stage9c_three_hour_soak_ledger import guard


def cohort_ids(conn):
    guard(conn)
    collectors = conn.execute(text("""
        SELECT collector_uuid,collector_name,hostname,egress_key,lane,
               enabled,drained,retired_at FROM collectors
    """)).mappings().all()
    if len(collectors) != 3:
        raise RuntimeError("collector count mismatch")
    for c in collectors:
        node = c["hostname"]
        if (node not in NODES or c["collector_uuid"] != UUIDS[node]
            or c["collector_name"] != RUN + ":" + node
            or c["egress_key"] != RUN + ":" + node
            or c["lane"] != "background" or not c["enabled"]
            or c["drained"] or c["retired_at"] is not None):
            raise RuntimeError("collector identity mismatch")
    soldiers = conn.execute(text("""
        SELECT soldier_id,persona_id,platform,current_name
        FROM soldiers ORDER BY soldier_id
    """)).mappings().all()
    expected = {(persona, "pc", name) for name, persona, _ in COHORT}
    actual = {(s["persona_id"], s["platform"], s["current_name"]) for s in soldiers}
    if len(soldiers) != 9 or actual != expected:
        raise RuntimeError("soldier cohort mismatch")
    return sorted(s["soldier_id"] for s in soldiers)
