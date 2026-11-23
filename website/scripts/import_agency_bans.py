#!/usr/bin/env python3
"""Bounded Agency ban-list import with authoritative persona mapping.

Run on bf4ps-db with peer-auth PostgreSQL. Import ONLY explicit active bans;
absence from the ban list never implies clean. Repeat pages as needed.
"""
import argparse
import json
import time
import uuid
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from sqlalchemy import create_engine,text

BASE='https://api.battlefield.agency'
UPSERT=text('''
INSERT INTO public.soldier_ban_status
(soldier_id,agency_player_uuid,ba_banned,ba_reason,ba_checked_at)
SELECT soldier_id,:uuid,TRUE,:reason,now()
FROM public.soldiers WHERE platform='pc' AND persona_id=:persona
ON CONFLICT (soldier_id) DO UPDATE SET
agency_player_uuid=EXCLUDED.agency_player_uuid,
ba_banned=TRUE,ba_reason=EXCLUDED.ba_reason,
ba_checked_at=EXCLUDED.ba_checked_at,updated_at=now()
''')

def get(path,params=None):
    url=BASE+path+('?' + urlencode(params) if params else '')
    with urlopen(Request(url,headers={'User-Agent':'BF4PlayerStats/1.0','Accept':'application/json'}),timeout=15) as response:
        return json.load(response)

def active(ban):
    # Historical NULL state is present on a confirmed active ban.
    return isinstance(ban,dict) and ban.get('state') in (None,'Active')

def run(engine,start_page,pages,size,delay,dry_run):
    seen=set();stats={'pages':0,'bans':0,'active':0,'players':0,'persona_ids':0,'matched_rows':0,'errors':0}
    for page in range(start_page,start_page+pages):
        listing=get('/api/ban/',{'page':page,'size':size})
        items=listing.get('items')
        if not isinstance(items,list):raise ValueError('Invalid Agency ban page')
        stats['pages']+=1;stats['bans']+=len(items)
        for ban in items:
            if not active(ban):continue
            stats['active']+=1
            player=ban.get('player') or {}
            raw_uuid=player.get('id')
            try: player_uuid=uuid.UUID(raw_uuid)
            except (TypeError,ValueError):stats['errors']+=1;continue
            if player_uuid in seen:continue
            seen.add(player_uuid)
            time.sleep(delay)
            try:
                detail=get('/api/player/'+str(player_uuid))
                if str(uuid.UUID(detail['id']))!=str(player_uuid):raise ValueError('Identity mismatch')
                personae=detail.get('personae')
                if not isinstance(personae,list):raise ValueError('Missing personae')
                stats['players']+=1
                ids={p['persona_id'] for p in personae if isinstance(p,dict) and p.get('game')=='bf4' and type(p.get('persona_id')) is int and p['persona_id']>0}
                stats['persona_ids']+=len(ids)
                reason=ban.get('reason')
                for persona in ids:
                    if not dry_run:
                        with engine.begin() as conn:
                            result=conn.execute(UPSERT,{'uuid':player_uuid,'persona':persona,'reason':reason})
                            stats['matched_rows']+=result.rowcount
            except (OSError,ValueError,KeyError,TypeError) as exc:
                stats['errors']+=1
                print('identity_lookup_failed',str(player_uuid),type(exc).__name__,flush=True)
        print('page',page,'total',listing.get('total'),'stats',json.dumps(stats),flush=True)
        if len(items)<size:break
        time.sleep(delay)
    return stats

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--start-page',type=int,default=1)
    parser.add_argument('--pages',type=int,default=1)
    parser.add_argument('--size',type=int,default=100)
    parser.add_argument('--delay',type=float,default=1.0)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not 1<=args.start_page or not 1<=args.pages<=100 or not 1<=args.size<=100 or args.delay<0.5:parser.error('Invalid bounds (minimum delay 0.5s)')
    engine=create_engine('postgresql+psycopg:///bf4_playerstats') if args.apply else None
    print('mode', 'APPLY' if args.apply else 'DRY RUN',flush=True)
    run(engine,args.start_page,args.pages,args.size,args.delay,not args.apply)

if __name__=='__main__':main()
