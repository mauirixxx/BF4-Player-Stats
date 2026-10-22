"""PostgreSQL-backed singleton lease with database-time authority."""
from dataclasses import dataclass
import psycopg

LEASE_KEY = "discord:leader"

@dataclass(frozen=True)
class Lease:
    owner: str
    generation: int
    ttl_seconds: int

def heartbeat(dsn: str, node: str) -> None:
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE bot_nodes SET last_heartbeat_at=clock_timestamp(),updated_at=clock_timestamp() WHERE node_id=%s", (node,))
            if cur.rowcount != 1:
                raise RuntimeError(f"Unknown node {node}")

def acquire(dsn: str, node: str, ttl: int = 30) -> Lease | None:
    """Atomic acquisition. Does not preempt an unexpired lease."""
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT enabled,draining FROM bot_nodes WHERE node_id=%s FOR UPDATE", (node,))
            eligibility=cur.fetchone()
            if not eligibility or not eligibility[0] or eligibility[1]:
                return None
            cur.execute("SELECT owner_node_id,generation,expires_at FROM bot_leases WHERE lease_key=%s FOR UPDATE", (LEASE_KEY,))
            row=cur.fetchone()
            if row is None: raise RuntimeError("Missing initial Discord lease")
            old_owner,generation,expires=row
            cur.execute("SELECT clock_timestamp()")
            now=cur.fetchone()[0]
            if old_owner is not None and expires is not None and expires > now:
                return None
            cur.execute("""UPDATE bot_leases SET owner_node_id=%s,generation=generation+1,
                acquired_at=clock_timestamp(),renewed_at=clock_timestamp(),
                expires_at=clock_timestamp()+(%s * interval '1 second')
                WHERE lease_key=%s RETURNING generation""",(node,ttl,LEASE_KEY))
            new_generation=cur.fetchone()[0]
            cur.execute("""INSERT INTO bot_leadership_history
                (lease_key,event_type,previous_owner_node_id,new_owner_node_id,previous_generation,new_generation,reason)
                VALUES (%s,'acquired',%s,%s,%s,%s,'lease_expired_or_unowned')""",
                (LEASE_KEY,old_owner,node,generation,new_generation))
            return Lease(node,new_generation,ttl)

def renew(dsn: str, node: str, generation: int, ttl: int = 30) -> bool:
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("""UPDATE bot_leases l SET renewed_at=clock_timestamp(),
                expires_at=clock_timestamp()+(%s * interval '1 second')
                WHERE l.lease_key=%s AND l.owner_node_id=%s AND l.generation=%s
                AND l.expires_at>clock_timestamp()
                AND EXISTS (SELECT 1 FROM bot_nodes n WHERE n.node_id=%s
                AND n.enabled AND NOT n.draining)
                RETURNING l.generation""",(ttl,LEASE_KEY,node,generation,node))
            return cur.fetchone() is not None

def release(dsn: str, node: str, generation: int) -> bool:
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("""UPDATE bot_leases SET owner_node_id=NULL,expires_at=clock_timestamp(),
                renewed_at=clock_timestamp() WHERE lease_key=%s AND owner_node_id=%s
                AND generation=%s RETURNING generation""",(LEASE_KEY,node,generation))
            if cur.fetchone() is None: return False
            cur.execute("""INSERT INTO bot_leadership_history
                (lease_key,event_type,previous_owner_node_id,new_owner_node_id,previous_generation,new_generation,reason)
                VALUES (%s,'released',%s,NULL,%s,%s,'graceful_shutdown')""",
                (LEASE_KEY,node,generation,generation))
            return True
