"""Bounded read-only platoon endpoints. Database schema follows legacy exporter."""
from sqlalchemy import text

LIST_SQL = text("""SELECT platoon_id::text AS id,name,tag,official_member_count,
battlelog_created_at::text AS created_at,last_success_at::text AS last_success_at,
website_url,emblem_path,
(SELECT count(*) FROM platoon_roster_accounts a WHERE a.platoon_id=platoons.platoon_id
AND a.is_current AND EXISTS (SELECT 1 FROM platoon_roster_personas x
WHERE x.platoon_id=a.platoon_id AND x.battlelog_account_id=a.battlelog_account_id
AND x.is_current AND x.battlelog_platform_code IN (1,32,64))) AS visible_member_count
FROM platoons WHERE (:search='' OR lower(name) LIKE :pattern OR lower(tag) LIKE :pattern)
ORDER BY
CASE WHEN :sort='members' AND :direction='asc' THEN official_member_count END ASC NULLS LAST,
CASE WHEN :sort='members' AND :direction='desc' THEN official_member_count END DESC NULLS LAST,
CASE WHEN :sort='created' AND :direction='asc' THEN battlelog_created_at END ASC NULLS LAST,
CASE WHEN :sort='created' AND :direction='desc' THEN battlelog_created_at END DESC NULLS LAST,
name,platoon_id LIMIT :lim OFFSET :off""")
COUNT_SQL = text("""SELECT count(*) FROM platoons WHERE (:search='' OR lower(name) LIKE :pattern OR lower(tag) LIKE :pattern)""")
DETAIL_SQL = text("""SELECT platoon_id::text AS id,name,tag,official_member_count,
battlelog_created_at::text AS created_at,last_success_at::text AS last_success_at,
website_url,emblem_path FROM platoons WHERE platoon_id=:pid""")
MEMBERS_SQL = text("""SELECT a.battlelog_account_id::text AS account_id,a.account_name,a.role,
COALESCE(json_agg(json_build_object('persona_id',x.persona_id::text,'persona_name',x.persona_name,
'platform',x.platform_family,'platform_code',x.battlelog_platform_code,'soldier_id',s.soldier_id::text)
ORDER BY x.platform_family,x.persona_name) FILTER (WHERE x.persona_id IS NOT NULL),'[]'::json) AS personas
FROM platoon_roster_accounts a LEFT JOIN platoon_roster_personas x ON
x.platoon_id=a.platoon_id AND x.battlelog_account_id=a.battlelog_account_id AND x.is_current
LEFT JOIN soldiers s ON s.persona_id=x.persona_id AND s.platform=CASE x.battlelog_platform_code
WHEN 1 THEN 'pc' WHEN 32 THEN 'ps4' WHEN 64 THEN 'xboxone' ELSE 'unsupported' END
WHERE a.platoon_id=:pid AND a.is_current
GROUP BY a.battlelog_account_id,a.account_name,a.role
ORDER BY CASE a.role WHEN 'founder' THEN 0 WHEN 'leader' THEN 1 ELSE 2 END,a.account_name NULLS LAST LIMIT 250""")
STATS_SQL = text("""SELECT DISTINCT ON (s.soldier_id) s.soldier_id::text AS soldier_id,
d.kills,d.deaths,d.time_played_seconds,d.total_score,d.source_fetched_at::text AS stats_fetched_at
FROM platoon_roster_personas x JOIN platoon_roster_accounts a ON
a.platoon_id=x.platoon_id AND a.battlelog_account_id=x.battlelog_account_id AND a.is_current
JOIN soldiers s ON s.persona_id=x.persona_id AND s.platform=CASE x.battlelog_platform_code
WHEN 1 THEN 'pc' WHEN 32 THEN 'ps4' WHEN 64 THEN 'xboxone' END
JOIN detailed_stats_current d ON d.soldier_id=s.soldier_id
WHERE x.platoon_id=:pid AND x.is_current AND x.battlelog_platform_code IN (1,32,64)
ORDER BY s.soldier_id,d.source_fetched_at DESC""")

def decorate_emblem(row):
    from pathlib import Path
    from hashlib import sha256
    template=row.pop('emblem_path',None)
    if isinstance(template,str) and '[SIZE]' in template:
        url=template.replace('[SIZE]','256').replace('[FORMAT]','png').replace('http://','https://',1)
        if url.startswith('https://eaassets-a.akamaihd.net/battlelog/prod/emblem/'):
            name=str(row['id'])+'-'+sha256(url.encode()).hexdigest()[:16]+'.png'
            if (Path('/var/www/bf4playerstats.com/assets/platoon-emblems')/name).is_file():
                row['emblem_url']='/assets/platoon-emblems/'+name
    if 'emblem_url' not in row:
        row['emblem_url']='/assets/platoon-emblems/default-emblem-320.png'
    return row

def list_platoons(conn,search='',page=1,sort='name',direction='asc'):
    search=search.strip().lower()
    if sort not in ('name','members','created') or direction not in ('asc','desc'):raise ValueError('Invalid sort')
    params={'search':search,'pattern':'%'+search+'%','lim':50,'off':(page-1)*50,'sort':sort,'direction':direction}
    total=conn.execute(COUNT_SQL,params).scalar_one()
    rows=[decorate_emblem(dict(r)) for r in conn.execute(LIST_SQL,params).mappings()]
    return {'platoons':rows,'total':total,'page':page,'page_size':50}

def platoon_detail(conn,pid):
    row=conn.execute(DETAIL_SQL,{'pid':pid}).mappings().first()
    if row is None:return None
    p=decorate_emblem(dict(row))
    members=[dict(r) for r in conn.execute(MEMBERS_SQL,{'pid':pid}).mappings()]
    for m in members:m['personas']=[x for x in m['personas'] if int(x['platform_code']) in (1,32,64)]
    members=[m for m in members if m['personas']]
    p['members']=members
    p['visible_member_count']=len(members)
    stats=[dict(r) for r in conn.execute(STATS_SQL,{'pid':pid}).mappings()]
    p['soldier_stats']={r.pop('soldier_id'):r for r in stats}
    p['supported_soldier_count']=len({str(x['persona_id'])+':'+str(x['platform_code']) for m in members for x in m['personas']})
    return p

ASSOCIATIONS_SQL=text("""SELECT DISTINCT p.platoon_id::text AS id,p.name,p.tag
FROM platoon_roster_personas x JOIN platoon_roster_accounts a ON
a.platoon_id=x.platoon_id AND a.battlelog_account_id=x.battlelog_account_id AND a.is_current
JOIN platoons p ON p.platoon_id=x.platoon_id
WHERE x.persona_id=:persona AND x.battlelog_platform_code=:platform AND x.is_current
ORDER BY p.name LIMIT 100""")
OBSERVED_SQL=text("""SELECT d.linked_platoon_id::text AS platoon_id,d.last_checked_at::text AS observed_at
FROM platoon_soldier_discovery d JOIN soldiers s ON s.soldier_id=d.soldier_id
WHERE s.persona_id=:persona AND s.platform=:platform AND d.linked_platoon_id IS NOT NULL
ORDER BY d.last_checked_at DESC LIMIT 1""")
def soldier_platoons(conn,persona,platform):
    code={'pc':1,'ps4':32,'xboxone':64}[platform]
    matches=[dict(r) for r in conn.execute(ASSOCIATIONS_SQL,{'persona':persona,'platform':code}).mappings()]
    observed=conn.execute(OBSERVED_SQL,{'persona':persona,'platform':platform}).mappings().first()
    return {'platoons':matches,'observed':dict(observed) if observed else None}
