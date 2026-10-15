#!/usr/bin/env python3
"""BF4PS scratch leaderboard read API. SELECT-only SQL; no collector mutations."""
import json, os, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from sqlalchemy import create_engine, text
from general_leaderboard import query_page as get_general_page, METRICS as GENERAL_METRICS
from global_soldier_search import search_soldiers
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
        table,key=('weapon_catalog','weapon_id') if kind=='weapon' else ('vehicle_catalog','vehicle_id')
        rows=[dict(r) for r in conn.execute(text(f'SELECT {key} AS id,name,category FROM {table} ORDER BY name LIMIT 400')).mappings()]
        if kind == 'weapon':
            # Fast cross-catalog deduplication: inspect only raw keys appearing
            # in both catalogs. Avoid a full per-soldier weapon census here;
            # that query exceeds the 5-second request statement timeout.
            duplicates = conn.execute(text("""
                SELECT wc.weapon_id AS id, wc.name
                FROM weapon_catalog wc JOIN vehicle_catalog vc ON vc.name=wc.name
            """)).mappings().all()
            if duplicates:
                ids = [int(r['id']) for r in duplicates]
                weapon_positive = {int(r['weapon_id']) for r in conn.execute(text("""
                    SELECT DISTINCT weapon_id FROM soldier_weapon_stats
                    WHERE weapon_id = ANY(:ids) AND kills > 0
                    LIMIT 100
                """), {'ids': ids}).mappings()}
                vehicle_positive = {r['name'] for r in conn.execute(text("""
                    SELECT DISTINCT vc.name
                    FROM soldier_vehicle_stats vs
                    JOIN vehicle_catalog vc ON vc.vehicle_id=vs.vehicle_id
                    WHERE vc.name = ANY(:names) AND vs.kills > 0
                """), {'names': [r['name'] for r in duplicates]}).mappings()}
                hidden = {int(r['id']) for r in duplicates
                          if int(r['id']) not in weapon_positive and r['name'] in vehicle_positive}
                rows = [r for r in rows if int(r['id']) not in hidden]
        if kind=='vehicle':
            # Display one catalog entry per audited canonical family; the
            # ranked-detail query still performs MAX/SUM per soldier.
            hidden={raw for raw,(canonical,_) in VEHICLE_FAMILIES.items() if raw!=canonical}
            hidden.add(82)  # audited redundant unshielded .50 CAL
            # Zero-only placeholder IDs are hidden pending new evidence.
            hidden.update(ZERO_ONLY_VEHICLE_IDS)
            rows=[r for r in rows if r['id'] not in hidden]
        return rows
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
def get_page(conn, kind, platform, item, page, page_size, search, division):
    # Rank over full cohort; return one bounded page.
    stats, cat, key, state = KINDS[kind]
    params = {'platform':platform, 'item':item, 'search':'%'+search.lower()+'%',
              'division':division, 'limit':page_size, 'offset':(page-1)*page_size}
    platform_clause = '' if platform == 'all' else 'AND s.platform=:platform'
    if kind == 'vehicle':
        params['item'] = VEHICLE_FAMILIES.get(item,(item,None))[0]
        family = vehicle_family_sql().replace('t.vehicle_id','raw.vehicle_id')
        mode = vehicle_mode_sql().replace('t.vehicle_id','raw.vehicle_id')
        source=f'''WITH raw_per_soldier AS (
            SELECT s.soldier_id,t.vehicle_id,max(t.kills) AS kills,
                   max(t.source_fetched_at) AS source_fetched_at
            FROM soldier_vehicle_stats t JOIN soldiers s ON s.soldier_id=t.soldier_id
            JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            WHERE cs.vehicles_state='success' {platform_clause}
            GROUP BY s.soldier_id,t.vehicle_id
        ), variants AS (
            SELECT raw.soldier_id,{family} AS item_id,{mode} AS mode,
                   raw.kills,raw.source_fetched_at FROM raw_per_soldier raw
        ), consolidated AS (
            SELECT soldier_id,item_id,
                   CASE WHEN max(mode)='sum' THEN sum(kills) ELSE max(kills) END AS kills,
                   max(source_fetched_at) AS source_fetched_at
            FROM variants GROUP BY soldier_id,item_id
        ), cohort AS (
            SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
                   c.kills,c.source_fetched_at FROM consolidated c
            JOIN soldiers s ON s.soldier_id=c.soldier_id WHERE c.item_id=:item
        )'''
    else:
        source=f'''WITH cohort AS (
            SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
                   max(t.kills) AS kills,max(t.source_fetched_at) AS source_fetched_at
            FROM soldier_weapon_stats t JOIN soldiers s ON s.soldier_id=t.soldier_id
            JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            WHERE t.weapon_id=:item AND cs.weapons_state='success' {platform_clause}
            GROUP BY s.soldier_id,s.current_name,s.persona_id,s.platform
        )'''
    ranked=source+''', ranked AS (
        SELECT cohort.*,rank() OVER (ORDER BY kills DESC) AS rank,
               count(*) OVER () AS population FROM cohort
    ), filtered AS (
        SELECT *,rank * 100.0 / nullif(population,0) AS top_pct,
          CASE WHEN rank * 100.0 / nullif(population,0) <= 3 THEN 1
               WHEN rank * 100.0 / nullif(population,0) <= 8 THEN 2
               WHEN rank * 100.0 / nullif(population,0) <= 15 THEN 3
               WHEN rank * 100.0 / nullif(population,0) <= 25 THEN 4
               WHEN rank * 100.0 / nullif(population,0) <= 35 THEN 5
               WHEN rank * 100.0 / nullif(population,0) <= 50 THEN 6
               WHEN rank * 100.0 / nullif(population,0) <= 65 THEN 7
               WHEN rank * 100.0 / nullif(population,0) <= 80 THEN 8
               WHEN rank * 100.0 / nullif(population,0) <= 90 THEN 9 ELSE 10 END AS division
        FROM ranked WHERE (:search='%%' OR lower(current_name) LIKE :search
                            OR persona_id::text LIKE :search)
    )'''
    # Division must be applied after full-cohort ranking; metadata is independent of page.
    filter_clause='WHERE (:division=0 OR division=:division)'
    meta=conn.execute(text(ranked+f''' SELECT count(*) AS filtered_count,
        coalesce(max(population),0) AS population FROM filtered {filter_clause}'''),params).mappings().one()
    population=int(meta['population'])
    if population == 0:
        population=int(conn.execute(text(source+' SELECT count(*) FROM cohort'),params).scalar_one())
    result=[dict(r) for r in conn.execute(text(ranked+f'''
        SELECT soldier_id,current_name,persona_id,platform,kills,source_fetched_at,
               rank,top_pct,division FROM filtered {filter_clause}
        ORDER BY kills DESC,soldier_id LIMIT :limit OFFSET :offset
    '''),params).mappings()]
    return {'population':population,'filtered_count':int(meta['filtered_count']),
            'page':page,'page_size':page_size,'total_pages':(int(meta['filtered_count'])+page_size-1)//page_size,
            'rows':result}

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
            if u.path in ('/aliases','/alias-search'):
                with engine.connect() as c:
                    c.execute(text('SET TRANSACTION READ ONLY'))
                    c.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                    if u.path=='/aliases':
                        raw=q.get('soldier_id',[''])[0]
                        if not raw.isdecimal() or len(raw)>18: self.send_error(400);return
                        result=[dict(row) for row in c.execute(text("""SELECT name,first_seen_at::text AS first_seen_at,last_seen_at::text AS last_seen_at FROM public.soldier_names WHERE soldier_id=:id ORDER BY last_seen_at DESC,name LIMIT 200"""),{'id':int(raw)}).mappings()]
                    else:
                        term=q.get('q',[''])[0].strip()
                        if len(term)<2 or len(term)>80: self.send_error(400);return
                        result=[dict(row) for row in c.execute(text("""SELECT DISTINCT n.soldier_id FROM public.soldier_names n WHERE lower(n.name) LIKE :pattern LIMIT 100"""),{'pattern':'%'+term.lower()+'%'}).mappings()]
                send_json(self,200,{'rows':result});return
            if u.path=='/global-soldier-search':
                term=q.get('q',[''])[0].strip()
                if not 2<=len(term)<=80:
                    self.send_error(400);return
                with engine.connect() as c:
                    c.execute(text('SET TRANSACTION READ ONLY'))
                    c.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                    result=search_soldiers(c,term)
                send_json(self,200,result);return
            if u.path=='/general-leaderboard':
                metric=q.get('metric',['kills'])[0]
                platform=q.get('platform',['all'])[0]
                search=q.get('search',[''])[0].strip()
                try:
                    page=int(q.get('page',['1'])[0])
                    page_size=int(q.get('page_size',['50'])[0])
                    division=int(q.get('division',['0'])[0])
                except ValueError:
                    self.send_error(400);return
                if (metric not in GENERAL_METRICS or platform not in PLATFORMS
                    or not 1<=page<=100000 or not 1<=page_size<=100
                    or not 0<=division<=10 or len(search)>100):
                    self.send_error(400);return
                with engine.connect() as c:
                    if c.execute(text('select current_database()')).scalar_one()!='bf4_playerstats':
                        raise RuntimeError('Unexpected database')
                    c.execute(text('SET TRANSACTION READ ONLY'))
                    c.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                    result=get_general_page(c,metric,platform,page,page_size,search,division)
                send_json(self,200,result);return
            if u.path!='/leaderboard':self.send_error(404);return
            kind=q.get('kind',[''])[0];platform=q.get('platform',[''])[0];item=q.get('item',[None])[0]
            if kind not in KINDS or platform not in PLATFORMS or (item is not None and (not item.isdecimal() or len(item)>12)):
                self.send_error(400);return
            paging = item is not None and any(k in q for k in ('page','page_size','search','division'))
            try:
                page=int(q.get('page',['1'])[0]); page_size=int(q.get('page_size',['50'])[0]);
                division=int(q.get('division',['0'])[0]); search=q.get('search',[''])[0].strip()
            except ValueError:
                self.send_error(400);return
            if not 1<=page<=100000 or not 1<=page_size<=100 or not 0<=division<=10 or len(search)>100:
                self.send_error(400);return
            with engine.connect() as c:
                if c.execute(text('select current_database()')).scalar_one()!='bf4_playerstats':
                    raise RuntimeError('Only D3 scratch database permitted')
                c.execute(text('SET TRANSACTION READ ONLY'))
                c.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                result=(get_page(c,kind,platform,int(item),page,page_size,search,division)
                        if paging else get(c,kind,platform,int(item) if item is not None else None))
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
