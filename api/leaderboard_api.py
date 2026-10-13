#!/usr/bin/env python3
"""BF4PS scratch leaderboard read API. SELECT-only SQL; no collector mutations."""
import json, os, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from sqlalchemy import create_engine, text
engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True,pool_size=3,max_overflow=2)
MAINTENANCE_FILE=Path(os.environ.get('BF4PS_SITE_CONFIG','/etc/bf4ps-website/site.env'))
def maintenance_enabled():
    try:
        for line in MAINTENANCE_FILE.read_text().splitlines():
            if line.strip().startswith('MAINTENANCE_MODE='):
                return line.split('=',1)[1].strip().lower() == 'true'
    except FileNotFoundError:
        pass
    return False

def send_json(handler,status,payload):
    body=json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header('Content-Type','application/json')
    handler.send_header('Cache-Control','no-store')
    handler.send_header('X-Content-Type-Options','nosniff')
    if status==503:handler.send_header('Retry-After','30')
    handler.send_header('Content-Length',str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

PLATFORMS={'pc','ps4','xboxone','all'}
KINDS={'weapon':('soldier_weapon_stats','weapon_catalog','weapon_id','weapons_state'),
       'vehicle':('soldier_vehicle_stats','vehicle_catalog','vehicle_id','vehicles_state')}
# Catalog IDs 10 and 54 are two Battlelog UCAV variants carrying duplicate totals.
# Canonicalize them in the read model, never sum the duplicate per-soldier rows.
def get(conn,kind,platform,item):
    stats,cat,key,state=KINDS[kind]
    canonical=(f'CASE WHEN t.{key}=54 THEN 10 ELSE t.{key} END' if kind=='vehicle' else f't.{key}')
    where_platform='' if platform=='all' else 'AND s.platform=:platform'
    params={'platform':platform}
    if item is None:
        return [dict(r) for r in conn.execute(text(f"""
          WITH per_soldier AS (
            SELECT s.soldier_id,{canonical} AS item_id,max(t.kills) AS kills
            FROM {stats} t JOIN soldiers s ON s.soldier_id=t.soldier_id
            JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            WHERE cs.{state}='success' {where_platform}
            GROUP BY s.soldier_id,{canonical}
          )
          SELECT c.{key} AS id,c.name,c.category,count(*) AS collected_soldiers,
                 coalesce(sum(p.kills),0) AS total_kills
          FROM per_soldier p JOIN {cat} c ON c.{key}=p.item_id
          GROUP BY c.{key},c.name,c.category
          ORDER BY total_kills DESC,c.name LIMIT 400
        """),params).mappings()]
    canonical_item=10 if kind=='vehicle' and item==54 else item
    params['item']=canonical_item
    base=f"""FROM {stats} t JOIN soldiers s ON s.soldier_id=t.soldier_id
       JOIN collection_state cs ON cs.soldier_id=s.soldier_id
       WHERE {canonical}=:item AND cs.{state}='success' {where_platform}"""
    population=conn.execute(text(f'SELECT count(DISTINCT s.soldier_id) {base}'),params).scalar_one()
    rows=[dict(r) for r in conn.execute(text(f"""
       SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,max(t.kills) AS kills,
              max(t.source_fetched_at) AS source_fetched_at
       {base}
       GROUP BY s.soldier_id,s.current_name,s.persona_id,s.platform
       ORDER BY kills DESC,s.soldier_id
    """),params).mappings()]
    return {'population':population,'rows':rows}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            u=urlparse(self.path);q=parse_qs(u.query)
            if maintenance_enabled():
                send_json(self,503,{'status':'maintenance','message':'Statistics temporarily unavailable'});return
            if u.path=='/health':
                with engine.connect() as c:
                    if c.execute(text('select current_database()')).scalar_one()!='bf4ps_scratch_stage9c_d3':
                        raise RuntimeError('Only D3 scratch database permitted')
                send_json(self,200,{'status':'ok'});return
            if u.path!='/leaderboard':self.send_error(404);return
            kind=q.get('kind',[''])[0];platform=q.get('platform',[''])[0];item=q.get('item',[None])[0]
            if kind not in KINDS or platform not in PLATFORMS or (item is not None and (not item.isdecimal() or len(item)>12)):
                self.send_error(400);return
            with engine.connect() as c:
                if c.execute(text('select current_database()')).scalar_one()!='bf4ps_scratch_stage9c_d3':
                    raise RuntimeError('Only D3 scratch database permitted')
                c.execute(text('SET TRANSACTION READ ONLY'))
                result=get(c,kind,platform,int(item) if item is not None else None)
            body=json.dumps(result,default=str).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        except Exception as exc:
            print('leaderboard error',type(exc).__name__,str(exc)[:160],flush=True)
            send_json(self,503,{'status':'unavailable','message':'Statistics temporarily unavailable'})
    def log_message(self,*args):pass
if __name__=='__main__':
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
