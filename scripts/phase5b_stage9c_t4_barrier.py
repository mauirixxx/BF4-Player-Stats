"""T4 scratch-only coordination events. Never used by production collectors."""
from __future__ import annotations
from sqlalchemy import text

READY = "stage9c_t4_ready"
RELEASE = "stage9c_t4_release"
DONE = "stage9c_t4_done"
HOSTS = frozenset(("tcou", "hnl-01", "kah-01"))

def events(conn, marker, event_type):
    return conn.execute(text("""
        SELECT metadata->>'host' AS host, metadata->>'outcome' AS outcome
        FROM collection_events
        WHERE event_type=:kind AND metadata->>'stage9c_t4_marker'=:marker
        ORDER BY event_id
    """), {"kind":event_type,"marker":marker}).all()

def emit(conn, marker, event_type, host=None, outcome=None):
    conn.execute(text("""
        INSERT INTO collection_events(event_type,metadata)
        VALUES (:kind,jsonb_build_object('stage9c_t4_marker',CAST(:marker AS text),
                                        'host',CAST(:host AS text),
                                        'outcome',CAST(:outcome AS text)))
    """), {"kind":event_type,"marker":marker,"host":host,"outcome":outcome})

def verify_ready(conn, marker):
    ready=events(conn,marker,READY)
    if len(ready)!=3 or {r.host for r in ready}!=HOSTS:
        raise RuntimeError("REFUSING release without exactly three distinct ready hosts")
    return ready

def verify_done(conn, marker):
    done=events(conn,marker,DONE)
    if len(done)!=3 or {r.host for r in done}!=HOSTS:
        raise RuntimeError("REFUSING incomplete participant finish ledger")
    if sorted(r.outcome for r in done)!=["DENIED","DENIED","WIN"]:
        raise RuntimeError("REFUSING unexpected admission outcomes")
    return done
