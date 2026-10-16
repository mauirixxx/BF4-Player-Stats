"""Database-only moderation operations. NOT an HTTP endpoint.

The caller must independently enforce admin authentication, authorization,
CSRF, idempotency, and rate limits before invoking these functions. Call each
mutation inside a database transaction. No public web route imports this.
"""
from sqlalchemy import text

PLATFORMS = frozenset(('pc', 'ps4', 'xboxone'))
REASONS = frozenset(('data_integrity_anomaly', 'operator_review', 'duplicate_identity', 'other'))


def validate_identity(platform, persona_id):
    if platform not in PLATFORMS or not isinstance(persona_id, int) or isinstance(persona_id, bool) or not 0 < persona_id < 2**63:
        raise ValueError('invalid identity')


def get_exclusion(conn, *, platform, persona_id):
    validate_identity(platform, persona_id)
    return conn.execute(text('''
        SELECT platform,persona_id,reason_code,private_note,created_by,
               created_at,updated_at,active
        FROM public.player_exclusions
        WHERE platform=:platform AND persona_id=:persona_id
    '''), {'platform': platform, 'persona_id': persona_id}).mappings().one_or_none()


def set_exclusion(conn, *, platform, persona_id, active, actor, reason_code, private_note=None):
    """Record a reversible exclusion transition and audit, transactionally.

    Does not purge data or rebuild exports. Idempotent no-op on same state.
    The web layer must use a dedicated, narrowly privileged operator role.
    """
    validate_identity(platform, persona_id)
    if not isinstance(active, bool) or reason_code not in REASONS:
        raise ValueError('invalid moderation action')
    if not isinstance(actor, str) or not 1 <= len(actor) <= 128 or not actor.strip():
        raise ValueError('invalid actor')
    if private_note is not None and (not isinstance(private_note, str) or len(private_note) > 2000):
        raise ValueError('invalid note')
    params = dict(platform=platform, persona_id=persona_id, active=active,
                  actor=actor, reason_code=reason_code, private_note=private_note)
    # Serialize moderation for one identity, even if the row doesn't yet exist.
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:platform), :persona_id % 2147483647)'), params)
    previous = get_exclusion(conn, platform=platform, persona_id=persona_id)
    if previous is None and not active:
        raise ValueError('identity has no exclusion to restore')
    if previous is not None and bool(previous['active']) == active:
        return {'changed': False, 'active': active}
    conn.execute(text('''
        INSERT INTO public.player_exclusions
            (platform,persona_id,reason_code,private_note,created_by,active)
        VALUES (:platform,:persona_id,:reason_code,:private_note,:actor,:active)
        ON CONFLICT (platform,persona_id) DO UPDATE SET
            active=EXCLUDED.active,reason_code=EXCLUDED.reason_code,
            private_note=EXCLUDED.private_note,updated_at=now()
    '''), params)
    conn.execute(text('''
        INSERT INTO public.player_exclusion_audit
            (platform,persona_id,action,actor,reason_code,private_note)
        VALUES (:platform,:persona_id,:action,:actor,:reason_code,:private_note)
    '''), {**params, 'action': 'exclude' if active else 'restore'})
    return {'changed': True, 'active': active}
