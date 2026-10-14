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
# Audited D3 families. Values are (canonical ID, aggregation).
# SUM: distinct variants; MAX: overlapping/mirrored Battlelog statistics.
VEHICLE_FAMILIES = {
    2: (2, 'sum'), 30: (2, 'sum'),
    41: (41, 'sum'), 63: (41, 'sum'),
    47: (47, 'max'), 67: (47, 'max'),
    27: (27, 'max'), 5: (27, 'max'),
    46: (46, 'max'), 56: (46, 'max'),
    78: (78, 'max'), 68: (78, 'max'),
    4: (4, 'max'), 36: (4, 'max'), 23: (4, 'max'),
    1: (1, 'max'), 73: (1, 'max'),
    17: (17, 'max'), 15: (17, 'max'),
    52: (52, 'max'), 13: (52, 'max'),
    16: (16, 'max'), 76: (16, 'max'), 34: (16, 'max'),
    8: (8, 'max'), 21: (8, 'max'),
    10: (10, 'max'), 54: (10, 'max'),
}
# Suppress zero-only placeholder IDs only while they remain zero.
ZERO_ONLY_VEHICLE_IDS = {62, 26, 71, 55}

def vehicle_family_sql():
    cases = ' '.join(f'WHEN {raw} THEN {canonical}'
                     for raw, (canonical, _) in VEHICLE_FAMILIES.items())
    return f'CASE t.vehicle_id {cases} ELSE t.vehicle_id END'

def vehicle_mode_sql():
    sum_ids = sorted(k for k, (_, mode) in VEHICLE_FAMILIES.items() if mode == 'sum')
    return f"CASE WHEN t.vehicle_id IN ({','.join(map(str, sum_ids))}) THEN 'sum' ELSE 'max' END"

def get(conn,kind,platform,item):
    if item is None:
        table, key = ('weapon_catalog', 'weapon_id') if kind == 'weapon' else ('vehicle_catalog', 'vehicle_id')
        return [dict(row) for row in conn.execute(text(
            f'SELECT {key} AS id, name, category FROM {table} ORDER BY name LIMIT 400'
        )).mappings()]
    stats,cat,key,state=KINDS[kind]
    where_platform='' if platform=='all' else 'AND s.platform=:platform'
    params={'platform':platform}
    if kind == 'vehicle':
        family = vehicle_family_sql()
        mode = vehicle_mode_sql()
        # Deduplicate each raw ID first, then SUM distinct variants or MAX mirrors.
        # Both catalog and detail queries share this identical CTE.
        cte=f"""
          WITH raw_per_soldier AS (
            SELECT s.soldier_id,t.vehicle_id,max(t.kills) AS kills,
                   max(t.source_fetched_at) AS source_fetched_at
            FROM soldier_vehicle_stats t
            JOIN soldiers s ON s.soldier_id=t.soldier_id
            JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            WHERE cs.vehicles_state='success' {where_platform}
            GROUP BY s.soldier_id,t.vehicle_id
          ), per_soldier AS (
            SELECT raw.soldier_id,
                   {family.replace('t.vehicle_id','raw.vehicle_id')} AS item_id,
                   {mode.replace('t.vehicle_id','raw.vehicle_id')} AS mode,
                   raw.kills,raw.source_fetched_at
            FROM raw_per_soldier raw
          ), consolidated AS (
            SELECT soldier_id,item_id,
                   CASE WHEN max(mode)='sum' THEN sum(kills) ELSE max(kills) END AS kills,
                   max(source_fetched_at) AS source_fetched_at
            FROM per_soldier GROUP BY soldier_id,item_id
          )
        """
        # For zero-only placeholders, don't hide future nonzero data.
        # They are excluded from catalog only when their aggregated total is zero.
        if item is None:
            return [dict(r) for r in conn.execute(text(cte+f"""
                SELECT c.vehicle_id AS id,c.name,c.category,
                       count(*) AS collected_soldiers,
                       coalesce(sum(p.kills),0) AS total_kills
                FROM consolidated p JOIN vehicle_catalog c ON c.vehicle_id=p.item_id
                GROUP BY c.vehicle_id,c.name,c.category
                HAVING c.vehicle_id NOT IN ({','.join(map(str,sorted(ZERO_ONLY_VEHICLE_IDS)))})
                       OR coalesce(sum(p.kills),0)>0
                ORDER BY total_kills DESC,c.name LIMIT 400
            """),params).mappings()]
        canonical_item=VEHICLE_FAMILIES.get(item,(item,None))[0]
        params['item']=canonical_item
        result=[dict(r) for r in conn.execute(text(cte+"""
            SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
                   p.kills,p.source_fetched_at
            FROM consolidated p JOIN soldiers s ON s.soldier_id=p.soldier_id
            WHERE p.item_id=:item
            ORDER BY p.kills DESC,s.soldier_id
        """),params).mappings()]
        return {'population':len(result),'rows':result}
    canonical=f't.{key}'
    if item is None:
        catalog = [dict(r) for r in conn.execute(text(f"""
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
        # Cross-catalog zero-only visibility rule: only hide a zero-kill
        # entry when the identically named counterpart has positive kills
        # on the requested platform. Keep all source records untouched.
        if kind == 'weapon':
            zero_names = {r['name'] for r in catalog if int(r['total_kills']) == 0}
            if zero_names:
                counterpart = conn.execute(text("""
                    SELECT vc.name, COALESCE(SUM(vs.kills), 0) AS kills
                    FROM soldier_vehicle_stats vs
                    JOIN vehicle_catalog vc ON vc.vehicle_id = vs.vehicle_id
                    JOIN soldiers s ON s.soldier_id = vs.soldier_id
                    JOIN collection_state cs ON cs.soldier_id = s.soldier_id
                    WHERE cs.vehicles_state = 'success'
                      AND (:platform = 'all' OR s.platform = :platform)
                      AND vc.name = ANY(:names)
                    GROUP BY vc.name
                """), {'platform': platform, 'names': sorted(zero_names)}).mappings()
                active_names = {r['name'] for r in counterpart if int(r['kills']) > 0}
                catalog = [r for r in catalog if not (
                    r['name'] in active_names and int(r['total_kills']) == 0
                )]
        return catalog
    params['item']=item
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
                    if c.execute(text('select current_database()')).scalar_one()!='bf4_playerstats':
                        raise RuntimeError('Only D3 scratch database permitted')
                send_json(self,200,{'status':'ok'});return
            if u.path!='/leaderboard':self.send_error(404);return
            kind=q.get('kind',[''])[0];platform=q.get('platform',[''])[0];item=q.get('item',[None])[0]
            if kind not in KINDS or platform not in PLATFORMS or (item is not None and (not item.isdecimal() or len(item)>12)):
                self.send_error(400);return
            with engine.connect() as c:
                if c.execute(text('select current_database()')).scalar_one()!='bf4_playerstats':
                    raise RuntimeError('Only D3 scratch database permitted')
                c.execute(text('SET TRANSACTION READ ONLY'))
                c.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                result=get(c,kind,platform,int(item) if item is not None else None)
            body=json.dumps(result,default=str).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        except Exception as exc:
            print('leaderboard error',type(exc).__name__,str(exc)[:160],flush=True)
            send_json(self,503,{'status':'unavailable','message':'Statistics temporarily unavailable'})
    def log_message(self,*args):pass
if __name__=='__main__':
    port=int(os.environ.get('BF4PS_API_PORT','8765'))
    if not 1 <= port <= 65535:raise ValueError('Invalid BF4PS_API_PORT')
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
