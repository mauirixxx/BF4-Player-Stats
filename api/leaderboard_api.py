#!/usr/bin/env python3
"""BF4PS scratch leaderboard read API. SELECT-only SQL; no collector mutations."""
import json, os, time
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from sqlalchemy import create_engine, text
from general_leaderboard import query_page as get_general_page, METRICS as GENERAL_METRICS
from global_soldier_search import search_soldiers
from soldier_detail import get_soldier_detail
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
    body=json.dumps(payload,default=str).encode()
    handler.send_response(status)
    handler.send_header('Content-Type','application/json')
    handler.send_header('Cache-Control','no-store')
    handler.send_header('X-Content-Type-Options','nosniff')
    if status==503:handler.send_header('Retry-After','30')
    handler.send_header('Content-Length',str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

# Shared process-local cache for public equipment requests. Single-flight
# ensures only one DB load per key while other request threads wait.
_equipment_cache={}
_equipment_inflight={}
_equipment_cache_lock=threading.Lock()
_equipment_cache_stats={'hits':0,'misses':0,'waits':0,'loads':0,'errors':0}
def cached_equipment(key, ttl, load):
    with _equipment_cache_lock:
        hit=_equipment_cache.get(key)
        if hit and hit[0]>time.monotonic():
            _equipment_cache_stats['hits']+=1
            return hit[1]
        flight=_equipment_inflight.get(key)
        if flight is None:
            flight=threading.Event()
            _equipment_inflight[key]=flight
            leader=True
            _equipment_cache_stats['misses']+=1
        else:
            leader=False
            _equipment_cache_stats['waits']+=1
    if not leader:
        flight.wait()
        with _equipment_cache_lock:
            hit=_equipment_cache.get(key)
            if hit and hit[0]>time.monotonic():
                _equipment_cache_stats['hits']+=1
                return hit[1]
        # A failed or expired load must be retried, not cached as an error.
        return cached_equipment(key,ttl,load)
    try:
        result=load()
        with _equipment_cache_lock:
            if len(_equipment_cache)>=300:
                expired=[k for k,(expires,_) in _equipment_cache.items() if expires<=time.monotonic()]
                for k in expired: _equipment_cache.pop(k,None)
                if len(_equipment_cache)>=300:
                    _equipment_cache.pop(next(iter(_equipment_cache)))
            _equipment_cache[key]=(time.monotonic()+ttl,result)
            _equipment_cache_stats['loads']+=1
        return result
    except BaseException:
        with _equipment_cache_lock:
            _equipment_cache_stats['errors']+=1
        raise
    finally:
        with _equipment_cache_lock:
            _equipment_inflight.pop(key,None)
            flight.set()

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
            WHERE t.vehicle_id = ANY(:raw_ids) AND cs.vehicles_state='success' AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) {where_platform}
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
            WHERE p.item_id=:item AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
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
            WHERE cs.{state}='success' AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) {where_platform}
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
                      AND vc.name = ANY(:names) AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
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
       WHERE {canonical}=:item AND cs.{state}='success' AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) {where_platform}"""
    population=conn.execute(text(f'SELECT count(DISTINCT s.soldier_id) {base}'),params).scalar_one()
    rows=[dict(r) for r in conn.execute(text(f"""
       SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,max(t.kills) AS kills,
              max(t.source_fetched_at) AS source_fetched_at
       {base}
       GROUP BY s.soldier_id,s.current_name,s.persona_id,s.platform
       ORDER BY kills DESC,s.soldier_id
    """),params).mappings()]
    return {'population':population,'rows':rows}
def fast_weapon_kills_top10(conn, platform, item):
    # Indexed kills Top 10; population counted separately, no full-cohort window sort.

    # Only use for unfiltered page 1. Full ranking/search stays on get_page.
    params={'item':item,'platform':platform}
    eligible="""FROM soldier_weapon_stats t
      JOIN soldiers s ON s.soldier_id=t.soldier_id
      JOIN collection_state cs ON cs.soldier_id=s.soldier_id
      WHERE t.weapon_id=:item AND cs.weapons_state='success'
        AND (:platform='all' OR s.platform=:platform)
        AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe
          WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)"""
    population=int(conn.execute(text('SELECT count(DISTINCT s.soldier_id) '+eligible),params).scalar_one())
    rows=[dict(r) for r in conn.execute(text("""SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
        t.kills,t.source_fetched_at,
        CASE WHEN t.time_equipped_seconds>=60 THEN
          t.kills::numeric*60/t.time_equipped_seconds END AS kpm,
        CASE WHEN t.shots_fired>=100 AND t.shots_hit<=t.shots_fired THEN
          t.shots_hit::numeric*100/t.shots_fired END AS accuracy
        """+eligible+""" ORDER BY t.kills DESC,t.soldier_id LIMIT 10"""),params).mappings()]
    previous=None;rank=0
    for pos,row in enumerate(rows,1):
        if row['kills']!=previous:rank=pos
        previous=row['kills'];row['rank']=rank;row['position']=pos
        row['top_pct']=rank*100.0/population if population else 0
        pct=row['top_pct']
        row['division']=next((i for i,cutoff in enumerate((3,8,15,25,35,50,65,80,90),1) if pct<=cutoff),10)
    return {'population':population,'filtered_count':population,'page':1,'page_size':10,
            'total_pages':(population+9)//10,'rows':rows}

def indexed_equipment_top10(conn, kind, platform, item, sort_metric, page_size=10):
    # Bounded Top 10 from transactionally maintained derived metrics.
    # Revision 0013 read models already store canonical vehicle-family metrics
    # with the audited SUM/MAX consolidation applied by the writer. Revision
    # 0014 population metadata uses the same canonical IDs. Read these models
    # directly instead of re-aggregating the raw vehicle cohort per request.
    if kind == 'vehicle':
        item = VEHICLE_FAMILIES.get(item, (item, None))[0]
    table = 'weapon_leaderboard_metrics' if kind == 'weapon' else 'vehicle_leaderboard_metrics'
    column = 'weapon_id' if kind == 'weapon' else 'vehicle_id'
    if sort_metric == 'accuracy' and kind == 'vehicle':
        return None
    params = {'item': item, 'platform': platform, 'kind': kind, 'page_size': page_size}
    population = int(conn.execute(text('''
        SELECT coalesce(sum(population),0) FROM equipment_population
        WHERE kind=:kind AND item_id=:item
          AND (:platform='all' OR platform=:platform)
    '''), params).scalar_one())
    if not population:
        return {'population': 0, 'filtered_count': 0, 'page': 1,
                'page_size': page_size, 'total_pages': 0, 'rows': []}
    # Metric index provides ordered access; limit is applied before any
    # expensive full-population rank/window calculation.
    metric = {'kills': 'kills', 'kpm': 'kpm', 'accuracy': 'accuracy'}[sort_metric]
    accuracy = 'm.accuracy' if kind == 'weapon' else 'NULL::numeric'
    rows = [dict(r) for r in conn.execute(text(f'''
        SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
               m.kills,m.kpm,{accuracy} AS accuracy,m.source_fetched_at
        FROM {table} m JOIN soldiers s ON s.soldier_id=m.soldier_id
        WHERE m.{column}=:item
          AND (:platform='all' OR s.platform=:platform)
          AND NOT EXISTS (SELECT 1 FROM player_exclusions pe
              WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
        ORDER BY m.{metric} DESC NULLS LAST,m.soldier_id LIMIT :page_size
    '''), params).mappings()]
    # SQL rank() semantics: NULL values tie; ties share a rank.
    last = object()
    rank = 0
    for position, row in enumerate(rows, 1):
        value = row[sort_metric]
        if position == 1 or value != last:
            rank = position
        last = value
        row['rank'] = rank
        row['position'] = position
        row['top_pct'] = rank * 100.0 / population
        row['division'] = next((i for i, cutoff in enumerate((3,8,15,25,35,50,65,80,90), 1)
                                if row['top_pct'] <= cutoff), 10)
    return {'population': population, 'filtered_count': population, 'page': 1,
            'page_size': page_size, 'total_pages': (population + page_size - 1)//page_size, 'rows': rows}

def indexed_equipment_page(conn, kind, platform, item, page, page_size, sort_metric):
    # Bounded indexed OFFSET page; global tie rank is recovered from the first
    # score's cohort count rather than sorting the entire cohort with rank().
    if kind == 'vehicle':
        item = VEHICLE_FAMILIES.get(item, (item, None))[0]
    table = 'weapon_leaderboard_metrics' if kind == 'weapon' else 'vehicle_leaderboard_metrics'
    key = 'weapon_id' if kind == 'weapon' else 'vehicle_id'
    metric = {'kills':'kills','kpm':'kpm','accuracy':'accuracy'}[sort_metric]
    accuracy = 'm.accuracy' if kind == 'weapon' else 'NULL::numeric'
    params = {'item':item,'platform':platform,'kind':kind,
              'limit':page_size,'offset':(page-1)*page_size}
    population = int(conn.execute(text('''SELECT coalesce(sum(population),0)
        FROM equipment_population WHERE kind=:kind AND item_id=:item
        AND (:platform='all' OR platform=:platform)'''),params).scalar_one())
    common = f'''FROM {table} m JOIN soldiers s ON s.soldier_id=m.soldier_id
        WHERE m.{key}=:item AND (:platform='all' OR s.platform=:platform)
        AND NOT EXISTS (SELECT 1 FROM player_exclusions pe
          WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)'''
    rows=[dict(r) for r in conn.execute(text(f'''SELECT s.soldier_id,s.current_name,
        s.persona_id,s.platform,m.kills,m.kpm,{accuracy} AS accuracy,m.source_fetched_at
        {common} ORDER BY m.{metric} DESC NULLS LAST,m.soldier_id
        LIMIT :limit OFFSET :offset'''),params).mappings()]
    if rows:
        first=rows[0][sort_metric]
        ahead = ('m.'+metric+' > :first_score') if first is not None else ('m.'+metric+' IS NOT NULL')
        first_rank=int(conn.execute(text(f'SELECT count(*) {common} AND {ahead}'),
            {**params,'first_score':first}).scalar_one())+1
        rank=first_rank
        last=first
        for i,row in enumerate(rows):
            if i and row[sort_metric]!=last:
                rank=params['offset']+i+1
            last=row[sort_metric]
            row['rank']=rank
            row['position']=params['offset']+i+1
            row['top_pct']=rank*100.0/population
            row['division']=next((j for j,cutoff in enumerate((3,8,15,25,35,50,65,80,90),1)
                                   if row['top_pct']<=cutoff),10)
    return {'population':population,'filtered_count':population,'page':page,
            'page_size':page_size,'total_pages':(population+page_size-1)//page_size,
            'rows':rows}

def indexed_equipment_search(conn, kind, platform, item, search, sort_metric):
    # Canonical multi-ID vehicle families still use the legacy aggregation.
    if kind == 'vehicle':
        canonical = VEHICLE_FAMILIES.get(item, (item, None))[0]
        ids = {raw for raw, (family, _) in VEHICLE_FAMILIES.items() if family == canonical} | {canonical}
        item = canonical
    table = 'weapon_leaderboard_metrics' if kind == 'weapon' else 'vehicle_leaderboard_metrics'
    key = 'weapon_id' if kind == 'weapon' else 'vehicle_id'
    metric = {'kills': 'kills', 'kpm': 'kpm', 'accuracy': 'accuracy'}[sort_metric]
    accuracy = 'm.accuracy' if kind == 'weapon' else 'NULL::numeric'
    params = {'item':item,'platform':platform,'search':'%'+search.lower()+'%','kind':kind}
    # Restrict candidates before rank evaluation. Rank is calculated against
    # the whole eligible cohort, not just matching names.
    # Materialize name matches before joining the large equipment metrics cohort.
    # The metrics primary key is (soldier_id, item_id), so this stays bounded
    # by the matching identities rather than scanning all equipment owners.
    candidate_sql = f'''
      WITH matching_soldiers AS MATERIALIZED (
        SELECT s.soldier_id,s.current_name,s.persona_id,s.platform
        FROM soldiers s
        WHERE (:platform='all' OR s.platform=:platform)
          AND (lower(s.current_name) LIKE :search OR s.persona_id::text LIKE :search)
          AND NOT EXISTS (SELECT 1 FROM player_exclusions e
            WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)
      )
      SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
        m.kills,m.kpm,{accuracy} AS accuracy,m.source_fetched_at
      FROM matching_soldiers s JOIN {table} m
        ON m.soldier_id=s.soldier_id AND m.{key}=:item
    '''''
    candidate_rows = conn.execute(text(candidate_sql),params).mappings().all()
    count = len(candidate_rows)
    if count > 50:
        return None  # Very broad searches retain the existing full-cohort path.
    candidates = sorted(candidate_rows,
      key=lambda r: (r[metric] is None, -(r[metric] or 0), r['soldier_id']))[:50]
    population = int(conn.execute(text('''SELECT coalesce(sum(population),0)
      FROM equipment_population WHERE kind=:kind AND item_id=:item
      AND (:platform='all' OR platform=:platform)'''),params).scalar_one())
    if count <= 2:
        rows=[]
        for candidate in candidates:
            row=dict(candidate)
            value=row[metric]
            # rank() treats NULL as a single final tie group. position uses soldier_id.
            # Score comparisons use the same NULLS LAST ordering as the leaderboard.
            score_where = f'(m.{metric} > :score)' if value is not None else f'(m.{metric} IS NOT NULL)'
            position_where = (f'({score_where} OR (m.{metric} = :score AND m.soldier_id < :sid))'
                              if value is not None else f'({score_where} OR (m.{metric} IS NULL AND m.soldier_id < :sid))')
            common = f'''FROM {table} m JOIN soldiers s ON s.soldier_id=m.soldier_id
              WHERE m.{key}=:item AND (:platform='all' OR s.platform=:platform)
              AND NOT EXISTS (SELECT 1 FROM player_exclusions e
                WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)'''
            extra={**params,'score':value,'sid':row['soldier_id']}
            rank_ahead=int(conn.execute(text(f'SELECT count(*) {common} AND {score_where}'),extra).scalar_one())
            position_ahead=int(conn.execute(text(f'SELECT count(*) {common} AND {position_where}'),extra).scalar_one())
            row['rank']=rank_ahead+1
            row['position']=position_ahead+1
            row['top_pct']=row['rank']*100.0/population if population else None
            row['division']=next((i for i,c in enumerate((3,8,15,25,35,50,65,80,90),1) if row['top_pct'] is not None and row['top_pct']<=c),10)
            rows.append(row)
    else:
        # Rank all matched candidates in a single scan of the eligible cohort.
        # This avoids two full-cohort COUNT queries for every search hit.
        score_ahead = f'(c.{metric} > h.{metric})' if metric else 'FALSE'
        position_ahead = f'''(c.{metric} > h.{metric} OR
          (c.{metric} = h.{metric} AND c.soldier_id < h.soldier_id) OR
          (h.{metric} IS NULL AND (c.{metric} IS NOT NULL OR
            (c.{metric} IS NULL AND c.soldier_id < h.soldier_id))))'''
        sql=f'''WITH hits AS MATERIALIZED (
          SELECT m.soldier_id,m.{metric} FROM {table} m
          WHERE m.{key}=:item AND m.soldier_id=ANY(:hit_ids)
        ), cohort AS MATERIALIZED (
          SELECT m.soldier_id,m.{metric} FROM {table} m
          JOIN soldiers s ON s.soldier_id=m.soldier_id
          WHERE m.{key}=:item AND (:platform='all' OR s.platform=:platform)
            AND NOT EXISTS (SELECT 1 FROM player_exclusions e
              WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)
        ) SELECT h.soldier_id,
          1+count(*) FILTER (WHERE {score_ahead} OR (h.{metric} IS NULL AND c.{metric} IS NOT NULL)) AS rank,
          1+count(*) FILTER (WHERE {position_ahead}) AS position
        FROM hits h CROSS JOIN cohort c GROUP BY h.soldier_id,h.{metric}'''
        hit_ids=[r['soldier_id'] for r in candidates]
        ranks={r['soldier_id']:r for r in conn.execute(text(sql),{**params,'hit_ids':hit_ids}).mappings()}
        rows=[]
        for candidate in candidates:
            row=dict(candidate)
            row['rank']=int(ranks[row['soldier_id']]['rank'])
            row['position']=int(ranks[row['soldier_id']]['position'])
            row['top_pct']=row['rank']*100.0/population if population else None
            row['division']=next((i for i,c in enumerate((3,8,15,25,35,50,65,80,90),1) if row['top_pct'] is not None and row['top_pct']<=c),10)
            rows.append(row)
    return {'population':population,'filtered_count':int(count),'page':1,'page_size':50,
            'total_pages':(int(count)+49)//50,'rows':rows}

def get_page(conn, kind, platform, item, page, page_size, search, division, sort_metric="kills"):
    # Default OFF. Rank generations are not deployed to the production DB.
    # The adapter is imported only when explicitly enabled on a migrated
    # staging database. Any missing/stale generation uses the legacy path.
    if os.environ.get('BF4PS_PRECOMPUTED_RANK_READS') == '1':
        # Fail closed to the established query path until migration 0016
        # and the separate adapter have both been installed.
        revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        if revision == '0016_rank_scope_versions':
            try:
                from rank_read_path import get_precomputed_page
            except ModuleNotFoundError as exc:
                if exc.name != 'rank_read_path':
                    raise
            else:
                fast = get_precomputed_page(conn, kind, platform, item, page,
                                            page_size, search, division, sort_metric)
                if fast is not None:
                    return fast
    if page == 1 and page_size == 50 and search and division == 0:
        fast = indexed_equipment_search(conn, kind, platform, item, search, sort_metric)
        if fast is not None:
            return fast
    if page == 1 and page_size in (10, 50) and not search and division == 0:
        fast = indexed_equipment_top10(conn, kind, platform, item, sort_metric, page_size)
        if fast is not None:
            return fast
    if page > 1 and not search and division == 0:
        return indexed_equipment_page(conn, kind, platform, item, page, page_size, sort_metric)
    # Rank over full cohort; return one bounded page.
    stats, cat, key, state = KINDS[kind]
    params = {'platform':platform, 'item':item, 'search':'%'+search.lower()+'%',
              'division':division, 'limit':page_size, 'offset':(page-1)*page_size}
    platform_clause = '' if platform == 'all' else 'AND s.platform=:platform'
    if kind == 'vehicle':
        params['item'] = VEHICLE_FAMILIES.get(item,(item,None))[0]
        # Push the canonical-family restriction into the raw indexed scan.
        # Previously every vehicle record was aggregated for each Top 10 request.
        raw_ids=sorted({raw for raw,(canonical,_) in VEHICLE_FAMILIES.items() if canonical==params['item']} | {params['item']})
        params['raw_ids']=raw_ids
        family = vehicle_family_sql().replace('t.vehicle_id','raw.vehicle_id')
        mode = vehicle_mode_sql().replace('t.vehicle_id','raw.vehicle_id')
        source=f'''WITH raw_per_soldier AS (
            SELECT s.soldier_id,t.vehicle_id,max(t.kills) AS kills,max(t.time_in_seconds) AS usage_seconds,
                   max(t.source_fetched_at) AS source_fetched_at
            FROM soldier_vehicle_stats t JOIN soldiers s ON s.soldier_id=t.soldier_id
            JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            WHERE t.vehicle_id = ANY(:raw_ids) AND cs.vehicles_state='success' AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) {platform_clause}
            GROUP BY s.soldier_id,t.vehicle_id
        ), variants AS (
            SELECT raw.soldier_id,{family} AS item_id,{mode} AS mode,
                   raw.kills,raw.usage_seconds,raw.source_fetched_at FROM raw_per_soldier raw
        ), consolidated AS (
            SELECT soldier_id,item_id,
                   CASE WHEN max(mode)='sum' THEN sum(kills) ELSE max(kills) END AS kills,
                   CASE WHEN max(mode)='sum' THEN sum(usage_seconds) ELSE max(usage_seconds) END AS usage_seconds,
                   max(source_fetched_at) AS source_fetched_at
            FROM variants GROUP BY soldier_id,item_id
        ), cohort AS (
            SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
                   c.kills,c.usage_seconds,NULL::numeric AS accuracy,c.source_fetched_at FROM consolidated c
            JOIN soldiers s ON s.soldier_id=c.soldier_id WHERE c.item_id=:item AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
        )'''
    else:
        source=f'''WITH cohort AS (
            SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
                   max(t.kills) AS kills,max(t.time_equipped_seconds) AS usage_seconds,
                   CASE WHEN max(t.shots_fired)>=100 AND max(t.shots_hit)<=max(t.shots_fired) THEN
                     max(t.shots_hit)::numeric * 100 / max(t.shots_fired) ELSE NULL END AS accuracy,
                   max(t.source_fetched_at) AS source_fetched_at
            FROM soldier_weapon_stats t JOIN soldiers s ON s.soldier_id=t.soldier_id
            JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            WHERE t.weapon_id=:item AND cs.weapons_state='success' AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) {platform_clause}
            GROUP BY s.soldier_id,s.current_name,s.persona_id,s.platform
        )'''
    metric={'kills':'kills','kpm':'CASE WHEN usage_seconds>=60 THEN kills::numeric*60/usage_seconds END',
            'accuracy':'accuracy'}[sort_metric]
    # Undefined rates sort last. Tie-break deterministically by soldier_id.
    sort_sql=f'{metric} DESC NULLS LAST,soldier_id'
    ranked=source+f''', ranked AS (
        SELECT cohort.*,CASE WHEN usage_seconds>=60 THEN kills::numeric*60/usage_seconds END AS kpm,rank() OVER (ORDER BY {metric} DESC NULLS LAST) AS rank,
               row_number() OVER (ORDER BY {sort_sql}) AS position,
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
    # Common Top 10 request: population is already present on every ranked
    # row. Avoid running the same cohort/ranking CTE twice for metadata + rows.
    # This shortcut is ONLY for unfiltered page 1; all search/division
    # semantics remain on the existing full-cohort path.
    if page == 1 and not search and division == 0:
        result=[dict(r) for r in conn.execute(text(ranked+f'''
            SELECT soldier_id,current_name,persona_id,platform,kills,kpm,accuracy,source_fetched_at,
                   rank,position,top_pct,division,population
            FROM filtered ORDER BY {sort_sql} LIMIT :limit
        '''),params).mappings()]
        population=int(result[0]['population']) if result else 0
        for row in result:row.pop('population',None)
        return {'population':population,'filtered_count':population,
                'page':page,'page_size':page_size,
                'total_pages':(population+page_size-1)//page_size,'rows':result}
    # Division must be applied after full-cohort ranking; metadata is independent of page.
    filter_clause='WHERE (:division=0 OR division=:division)'
    meta=conn.execute(text(ranked+f''' SELECT count(*) AS filtered_count,
        coalesce(max(population),0) AS population FROM filtered {filter_clause}'''),params).mappings().one()
    population=int(meta['population'])
    if population == 0:
        population=int(conn.execute(text(source+' SELECT count(*) FROM cohort'),params).scalar_one())
    result=[dict(r) for r in conn.execute(text(ranked+f'''
        SELECT soldier_id,current_name,persona_id,platform,kills,kpm,accuracy,source_fetched_at,
               rank,position,top_pct,division FROM filtered {filter_clause}
        ORDER BY {sort_sql} LIMIT :limit OFFSET :offset
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
                        result=[dict(row) for row in c.execute(text("""SELECT n.name,n.first_seen_at::text AS first_seen_at,n.last_seen_at::text AS last_seen_at FROM public.soldier_names n JOIN public.soldiers s ON s.soldier_id=n.soldier_id WHERE n.soldier_id=:id AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) ORDER BY n.last_seen_at DESC,n.name LIMIT 200"""),{'id':int(raw)}).mappings()]
                    else:
                        term=q.get('q',[''])[0].strip()
                        if len(term)<2 or len(term)>80: self.send_error(400);return
                        result=[dict(row) for row in c.execute(text("""SELECT DISTINCT n.soldier_id FROM public.soldier_names n JOIN public.soldiers s ON s.soldier_id=n.soldier_id WHERE NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) AND lower(n.name) LIKE :pattern LIMIT 100"""),{'pattern':'%'+term.lower()+'%'}).mappings()]
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
            if u.path=='/linked-profiles':
                raw=q.get('soldier_id',[''])[0]
                if not raw.isdecimal() or len(raw)>19 or not 0<int(raw)<=9223372036854775807:
                    self.send_error(400);return
                with engine.connect() as c:
                    c.execute(text('SET TRANSACTION READ ONLY'))
                    c.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                    result=[dict(row) for row in c.execute(text("""
                        SELECT DISTINCT other.soldier_id,other.current_name,other.platform
                        FROM public.profile_soldiers source
                        JOIN public.soldiers origin ON origin.soldier_id=source.soldier_id
                        JOIN public.profile_soldiers related ON related.profile_id=source.profile_id
                        JOIN public.soldiers other ON other.soldier_id=related.soldier_id
                        WHERE source.soldier_id=:id AND other.soldier_id<>:id
                          AND NOT EXISTS (SELECT 1 FROM public.player_exclusions e
                            WHERE e.platform=origin.platform AND e.persona_id=origin.persona_id AND e.active)
                          AND NOT EXISTS (SELECT 1 FROM public.player_exclusions e
                            WHERE e.platform=other.platform AND e.persona_id=other.persona_id AND e.active)
                        ORDER BY other.platform,other.current_name,other.soldier_id LIMIT 30
                    """),{'id':int(raw)}).mappings()]
                send_json(self,200,{'rows':result});return
            if u.path=='/soldier-detail':
                raw=q.get('id',[''])[0]
                if not raw.isdecimal() or len(raw)>19 or int(raw)<1 or int(raw)>9223372036854775807:
                    self.send_error(400);return
                with engine.connect() as c:
                    c.execute(text('SET TRANSACTION READ ONLY'))
                    c.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                    result=get_soldier_detail(c,int(raw))
                if result is None:
                    send_json(self,404,{'error':'Soldier not found'});return
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
                    if not search and division==0 and page==1 and page_size==50:
                        result=cached_equipment(('general',metric,platform,page,page_size),300,
                            lambda: get_general_page(c,metric,platform,page,page_size,search,division))
                    else:
                        result=get_general_page(c,metric,platform,page,page_size,search,division)
                send_json(self,200,result);return
            if u.path!='/leaderboard':self.send_error(404);return
            kind=q.get('kind',[''])[0];platform=q.get('platform',[''])[0];item=q.get('item',[None])[0]
            if kind not in KINDS or platform not in PLATFORMS or (item is not None and (not item.isdecimal() or len(item)>12)):
                self.send_error(400);return
            paging = item is not None and any(k in q for k in ('page','page_size','search','division','sort'))
            try:
                page=int(q.get('page',['1'])[0]); page_size=int(q.get('page_size',['50'])[0]);
                division=int(q.get('division',['0'])[0]); search=q.get('search',[''])[0].strip()
            except ValueError:
                self.send_error(400);return
            sort_metric=q.get('sort',['kills'])[0]
            if sort_metric not in ('kills','kpm','accuracy') or (kind=='vehicle' and sort_metric=='accuracy'):
                self.send_error(400);return
            if not 1<=page<=100000 or not 1<=page_size<=100 or not 0<=division<=10 or len(search)>100:
                self.send_error(400);return
            with engine.connect() as c:
                if os.environ.get('BF4PS_PRECOMPUTED_RANK_READS') == '1':
                    # The version check and row read must share one MVCC snapshot.
                    c = c.execution_options(isolation_level='REPEATABLE READ')
                if c.execute(text('select current_database()')).scalar_one()!='bf4_playerstats':
                    raise RuntimeError('Only D3 scratch database permitted')
                c.execute(text('SET TRANSACTION READ ONLY'))
                c.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                c.execute(text("SET LOCAL statement_timeout = '12000ms'"))
                cache_key=(kind,platform,item,page,page_size,search,division,paging,sort_metric)
                # Public unfiltered first-page equipment Top 10 / Top 50: 300s.
                # Catalog: 60s. Searches, divisions, later pages: uncached.
                if os.environ.get('BF4PS_PRECOMPUTED_RANK_READS') != '1' and not search and (item is None or (paging and page==1 and page_size in (10,50) and division==0)):
                    ttl=60 if item is None else 300
                    result=cached_equipment(cache_key,ttl,
                        lambda: (get_page(c,kind,platform,int(item),page,page_size,search,division,sort_metric)
                            if paging else get(c,kind,platform,None)))
                else:
                    result=(get_page(c,kind,platform,int(item),page,page_size,search,division,sort_metric)
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
