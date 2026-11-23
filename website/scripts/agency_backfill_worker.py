#!/usr/bin/env python3
"""Resumable, bounded BA ban-list ingestion. A failed page is retried in full.

Use a single instance. Checkpoint only after every item on a page succeeds;
UPSERTs are idempotent. Periodically restart at page 1 to handle page drift.
"""
import argparse
import fcntl
import json
import os
import random
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError,URLError
from sqlalchemy import create_engine
from import_agency_bans import UPSERT,active,get


def request(path,params=None):
    for attempt in range(6):
        try:return get(path,params)
        except (HTTPError,URLError,TimeoutError,OSError) as exc:
            if isinstance(exc,HTTPError) and exc.code not in (429,500,502,503,504):raise
            if attempt==5:raise
            retry_after=exc.headers.get('Retry-After') if isinstance(exc,HTTPError) else None
            try:wait=max(1,min(300,float(retry_after))) if retry_after else min(90,2**attempt+random.random())
            except ValueError:wait=min(90,2**attempt+random.random())
            print('retry',path,type(exc).__name__,'wait',round(wait,1),flush=True)
            time.sleep(wait)

def atomic_save(path,state):
    tmp=path.with_suffix('.tmp')
    with open(tmp,'w') as f:
        json.dump(state,f,sort_keys=True);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def run(engine,path,max_pages,delay):
    state=json.loads(path.read_text()) if path.exists() else {'next_page':1,'completed_pages':0,'matched':0,'errors':0}
    page=int(state['next_page'])
    for _ in range(max_pages):
        listing=request('/api/ban/',{'page':page,'size':100})
        items=listing.get('items')
        if not isinstance(items,list):raise ValueError('Malformed Agency page')
        total=listing.get('total')
        if not isinstance(total,int) or total<0:raise ValueError('Malformed total')
        matched=0
        for ban in items:
            if not active(ban):continue
            raw=(ban.get('player') or {}).get('id')
            player_uuid=uuid.UUID(raw)
            time.sleep(delay)
            detail=request('/api/player/'+str(player_uuid))
            if uuid.UUID(detail['id'])!=player_uuid:raise ValueError('Agency UUID mismatch')
            personae=detail.get('personae')
            if not isinstance(personae,list):raise ValueError('Missing personae')
            ids={p['persona_id'] for p in personae if isinstance(p,dict) and p.get('game')=='bf4' and type(p.get('persona_id')) is int and p['persona_id']>0}
            for persona in ids:
                with engine.begin() as conn:
                    result=conn.execute(UPSERT,{'uuid':player_uuid,'persona':persona,'reason':ban.get('reason')})
                    matched+=result.rowcount
        state['completed_pages']+=1;state['matched']+=matched
        page=page+1 if len(items)==100 and page*100<total else 1
        state['next_page']=page
        atomic_save(path,state)
        print('checkpoint',json.dumps(state,sort_keys=True),flush=True)
        time.sleep(delay)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--state',type=Path,default=Path('/var/lib/bf4ps-ban-sync/agency-checkpoint.json'))
    p.add_argument('--max-pages',type=int,default=5)
    p.add_argument('--delay',type=float,default=1.0)
    args=p.parse_args()
    if not 1<=args.max_pages<=100 or args.delay<0.5:p.error('Invalid bounds')
    args.state.parent.mkdir(parents=True,exist_ok=True)
    with open(args.state.parent/'agency.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        engine=create_engine('postgresql+psycopg://bf4ps_ban_sync@/bf4_playerstats')
        run(engine,args.state,args.max_pages,args.delay)

if __name__=='__main__':main()
