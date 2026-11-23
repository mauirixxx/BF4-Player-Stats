#!/usr/bin/env python3
"""Explicit, rate-limited single-persona BA and BF4DB verification.

Requires BF4PS_DATABASE_URL. Never turns an API failure into a clean result.
Does not run on page views; use a controlled scheduled queue for backfills.
"""
import argparse
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import json
from sqlalchemy import create_engine, text

BASE = 'https://api.battlefield.agency'

def get(path, params=None):
    url = BASE + path + ('?' + urlencode(params) if params else '')
    with urlopen(Request(url, headers={'User-Agent':'BF4PlayerStats/1.0','Accept':'application/json'}), timeout=12) as r:
        if r.status != 200:
            raise ValueError('Unexpected API status')
        return json.load(r)

def fetch(persona):
    player = get('/api/player/by-persona_id/bf4/' + quote(str(persona), safe=''))
    if not isinstance(player,dict) or not player.get('id'):
        raise ValueError('Agency player identity unavailable')
    player_uuid = uuid.UUID(player['id'])
    bans = player.get('bans')
    ba = None
    reason = None
    if isinstance(bans,list):
        # Legacy null state is present on known historical bans. Never treat
        # unknown explicit state strings as an authoritative clean response.
        active = [b for b in bans if isinstance(b,dict) and b.get('state') in (None,'Active')]
        states = [b.get('state') for b in bans if isinstance(b,dict)]
        if active:
            ba = True
            reason = active[0].get('reason')
        elif not bans or all(state in ('Lifted','Lifted temporarily','Lifted due to policy') for state in states):
            ba = False
    bf4db = None
    bf4db_reason = None
    try:
        response = get('/api/bf4db/', {'player_ids':str(player_uuid)})
        item = response.get(str(player_uuid)) if isinstance(response,dict) else None
        if isinstance(item,dict) and type(item.get('banned')) is bool:
            bf4db = item['banned']
            bf4db_reason = item.get('reason')
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return player_uuid,ba,reason,bf4db,bf4db_reason

def save(engine,persona,result):
    player_uuid,ba,reason,bf4db,bf4db_reason=result
    with engine.begin() as conn:
        soldier=conn.execute(text("SELECT soldier_id FROM public.soldiers WHERE persona_id=:persona AND platform='pc'"),{'persona':persona}).scalar_one_or_none()
        if soldier is None:
            return False
        conn.execute(text('''
            INSERT INTO public.soldier_ban_status
            (soldier_id,agency_player_uuid,ba_banned,ba_reason,ba_checked_at,bf4db_banned,bf4db_reason,bf4db_checked_at)
            VALUES (:id,:uuid,:ba,:reason,CASE WHEN :ba IS NULL THEN NULL ELSE now() END,
                    :bf4db,:bf4db_reason,CASE WHEN :bf4db IS NULL THEN NULL ELSE now() END)
            ON CONFLICT (soldier_id) DO UPDATE SET
                agency_player_uuid=EXCLUDED.agency_player_uuid,
                ba_banned=COALESCE(EXCLUDED.ba_banned,public.soldier_ban_status.ba_banned),
                ba_reason=CASE WHEN EXCLUDED.ba_banned IS NULL THEN public.soldier_ban_status.ba_reason ELSE EXCLUDED.ba_reason END,
                ba_checked_at=COALESCE(EXCLUDED.ba_checked_at,public.soldier_ban_status.ba_checked_at),
                bf4db_banned=COALESCE(EXCLUDED.bf4db_banned,public.soldier_ban_status.bf4db_banned),
                bf4db_reason=CASE WHEN EXCLUDED.bf4db_banned IS NULL THEN public.soldier_ban_status.bf4db_reason ELSE EXCLUDED.bf4db_reason END,
                bf4db_checked_at=COALESCE(EXCLUDED.bf4db_checked_at,public.soldier_ban_status.bf4db_checked_at),
                updated_at=now()
        '''),{'id':soldier,'uuid':player_uuid,'ba':ba,'reason':reason,'bf4db':bf4db,'bf4db_reason':bf4db_reason})
        return True

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--persona-id',type=int,required=True)
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    if not 0 < args.persona_id <= 9223372036854775807:
        p.error('Invalid persona ID')
    result=fetch(args.persona_id)
    print('persona',args.persona_id,'agency_uuid',result[0],'BA',result[1],'BF4DB',result[3])
    if not args.dry_run:
        engine=create_engine(os.environ['BF4PS_DATABASE_URL'])
        print('saved',save(engine,args.persona_id,result))

if __name__=='__main__': main()
