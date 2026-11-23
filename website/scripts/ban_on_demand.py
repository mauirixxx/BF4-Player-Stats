#!/usr/bin/env python3
"""Internal, bounded on-demand BA/BF4DB cache refresh; never bulk-downloads."""
import json
import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from sqlalchemy import create_engine,text
from refresh_ban_status import fetch,save

DB='postgresql+psycopg://bf4ps_ban_sync@/bf4_playerstats'
ENGINE=create_engine(DB,pool_size=2,max_overflow=0)
WORK=queue.Queue(maxsize=64)
PENDING=set()
RETRY_AFTER={}
LOCK=threading.Lock()
TTL=timedelta(hours=24)
SQL=text('''SELECT s.persona_id,b.ba_checked_at,b.bf4db_checked_at
FROM public.soldiers s LEFT JOIN public.soldier_ban_status b ON b.soldier_id=s.soldier_id
WHERE s.soldier_id=:id AND s.platform='pc' AND NOT EXISTS (
SELECT 1 FROM public.player_exclusions e WHERE e.platform=s.platform
AND e.persona_id=s.persona_id AND e.active)''')

def enqueue(soldier_id):
    now=datetime.now(timezone.utc)
    with ENGINE.connect() as conn:
        row=conn.execute(SQL,{'id':soldier_id}).mappings().first()
    if row is None:return 'not_found'
    if all(row[k] is not None and row[k]>=now-TTL for k in ('ba_checked_at','bf4db_checked_at')):
        return 'fresh'
    with LOCK:
        if soldier_id in PENDING:return 'pending'
        if RETRY_AFTER.get(soldier_id,0)>time.monotonic():return 'cooldown'
        if WORK.full():return 'busy'
        PENDING.add(soldier_id)
        WORK.put_nowait((soldier_id,int(row['persona_id'])))
    return 'queued'

def worker():
    while True:
        soldier_id,persona=WORK.get()
        try:
            result=fetch(persona)
            save(ENGINE,persona,result)
            logging.info('verified soldier=%s BA=%s BF4DB=%s',soldier_id,result[1],result[3])
            cooldown=300
        except Exception as exc:
            logging.warning('verification failed soldier=%s type=%s',soldier_id,type(exc).__name__)
            cooldown=1800
        finally:
            with LOCK:
                RETRY_AFTER[soldier_id]=time.monotonic()+cooldown
                PENDING.discard(soldier_id)
                if len(RETRY_AFTER)>10000:
                    current=time.monotonic()
                    for k,v in list(RETRY_AFTER.items()):
                        if v<current:RETRY_AFTER.pop(k,None)
            WORK.task_done()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.client_address[0] not in ('127.0.0.1','192.168.10.71'):
            self.send_error(403);return
        u=urlsplit(self.path)
        if u.path!='/refresh':self.send_error(404);return
        raw=parse_qs(u.query).get('soldier_id',[''])[0]
        if not raw.isdecimal() or len(raw)>19 or not 0<int(raw)<=9223372036854775807:
            self.send_error(400);return
        status=enqueue(int(raw))
        body=json.dumps({'status':status}).encode()
        self.send_response(404 if status=='not_found' else 200)
        self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    threading.Thread(target=worker,daemon=True).start()
    ThreadingHTTPServer(('192.168.10.66',8770),Handler).serve_forever()
