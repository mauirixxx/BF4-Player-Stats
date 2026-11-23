#!/usr/bin/env python3
"""Bounded BF4DB refresh for cached Agency UUIDs, without BA status writes."""
import argparse
import json
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from sqlalchemy import create_engine,text

CANDIDATES=text('''SELECT soldier_id,agency_player_uuid FROM public.soldier_ban_status
WHERE agency_player_uuid IS NOT NULL
  AND (bf4db_checked_at IS NULL OR bf4db_checked_at < now()-interval '7 days')
ORDER BY bf4db_checked_at NULLS FIRST, soldier_id LIMIT :limit''')
SAVE=text('''UPDATE public.soldier_ban_status SET
bf4db_banned=:banned,bf4db_reason=:reason,bf4db_checked_at=now(),updated_at=now()
WHERE soldier_id=:soldier AND agency_player_uuid=:uuid''')

def fetch(uuid):
    url='https://api.battlefield.agency/api/bf4db/?'+urlencode({'player_ids':str(uuid)})
    with urlopen(Request(url,headers={'User-Agent':'BF4PlayerStats/1.0','Accept':'application/json'}),timeout=15) as response:
        data=json.load(response)
    item=data.get(str(uuid)) if isinstance(data,dict) else None
    if not isinstance(item,dict) or type(item.get('banned')) is not bool:
        raise ValueError('No authoritative BF4DB result')
    return item['banned'],item.get('reason')

def run(engine,limit,delay,apply):
    with engine.connect() as conn:
        candidates=list(conn.execute(CANDIDATES,{'limit':limit}).mappings())
    success=0;errors=0
    for row in candidates:
        time.sleep(delay)
        try:
            banned,reason=fetch(row['agency_player_uuid'])
            if apply:
                with engine.begin() as conn:
                    conn.execute(SAVE,{'soldier':row['soldier_id'],'uuid':row['agency_player_uuid'],'banned':banned,'reason':reason})
            success+=1
            print('soldier',row['soldier_id'],'bf4db',banned,flush=True)
        except (OSError,ValueError,TypeError,KeyError) as exc:
            errors+=1
            print('lookup_failed',row['soldier_id'],type(exc).__name__,flush=True)
    print('summary',{'candidates':len(candidates),'verified':success,'errors':errors,'applied':apply})

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--limit',type=int,default=10)
    p.add_argument('--delay',type=float,default=1.0)
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    if not 1<=args.limit<=500 or args.delay<0.5:p.error('Invalid bounds')
    engine=create_engine('postgresql+psycopg:///bf4_playerstats')
    run(engine,args.limit,args.delay,args.apply)

if __name__=='__main__':main()
