"""Trusted backend boundary for existing BF4 soldier manual requests.

No web server or credentials are activated by importing this module.
The API must authenticate through a separately restricted database role.
"""
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.engine import Engine
from bf4ps.manual_battlelog_url import parse_battlelog_soldier_url
from bf4ps.manual_request_admission import admit_registered_soldier


@dataclass(frozen=True)
class ManualRequestResponse:
    state: str
    request_id: int | None = None
    retry_after_seconds: int = 0
    jobs_created: int = 0
    jobs_promoted: int = 0


def submit_existing_soldier_url(engine: Engine, raw_url: str, *, kind: str = 'refresh') -> ManualRequestResponse:
    """Validate untrusted input, resolve authoritative identity, and commit atomically.

    A valid URL does not prove an identity exists. Never trust its display name
    for identity lookup; platform and persona ID are the unique key.
    """
    if kind not in ('add', 'refresh'):
        raise ValueError('unsupported request kind')
    soldier = parse_battlelog_soldier_url(raw_url)
    with engine.begin() as conn:
        soldier_id = conn.execute(text('''
            SELECT soldier_id FROM soldiers
            WHERE platform = :platform AND persona_id = :persona_id
        '''), {'platform': soldier.platform, 'persona_id': soldier.persona_id}).scalar_one_or_none()
        if soldier_id is None:
            return ManualRequestResponse('not_registered')
        admission = admit_registered_soldier(conn, soldier_id=int(soldier_id), kind=kind)
        if not admission.accepted:
            return ManualRequestResponse('cooldown', admission.request_id, admission.retry_after_seconds)
        return ManualRequestResponse('accepted', admission.request_id,
                                     jobs_created=len(admission.created),
                                     jobs_promoted=len(admission.promoted))