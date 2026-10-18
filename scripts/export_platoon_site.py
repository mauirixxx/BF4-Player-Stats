#!/usr/bin/env python3
"""Read-only bounded export for public platoon pages; atomically publish JSON."""
import argparse, json, os, tempfile, re, hashlib, urllib.request, time
from urllib.parse import urlsplit
from pathlib import Path
from sqlalchemy import create_engine, text

EMBLEM_DIR=Path("/var/www/bf4playerstats.com/assets/platoon-emblems")

def emblem_asset(platoon):
    template=platoon.get("emblem_path")
    if not isinstance(template,str):return None
    url=template.replace("[SIZE]","256").replace("[FORMAT]","png").replace("http://","https://",1)
    parsed=urlsplit(url)
    if parsed.scheme!="https" or parsed.hostname!="eaassets-a.akamaihd.net" or parsed.port not in (None,443) or parsed.username or parsed.password:return None
    if not re.fullmatch(r"/battlelog/prod/emblem/[0-9]+/[0-9]+/256/[0-9]+\.png",parsed.path):return None
    if not re.fullmatch(r"[0-9]+",str(platoon["id"])):return None
    digest=hashlib.sha256(url.encode()).hexdigest()[:16]
    return url,EMBLEM_DIR/(str(platoon["id"])+"-"+digest+".png")

def cache_emblems(platoons,limit=5):
    EMBLEM_DIR.mkdir(parents=True,exist_ok=True)
    attempts=0
    for p in platoons:
        item=emblem_asset(p)
        p.pop("emblem_path",None)
        if not item:continue
        url,path=item
        if path.exists():p["emblem_url"]="/assets/platoon-emblems/"+path.name;continue
        retry_marker=path.with_suffix(".retry")
        if retry_marker.exists() and time.time()-retry_marker.stat().st_mtime<21600:continue
        if attempts>=limit:continue
        attempts+=1
        tmp=None
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"BF4PSPlatoonEmblemCache/1.0"})
            with urllib.request.urlopen(req,timeout=8) as response:
                if response.status!=200 or response.headers.get_content_type()!="image/png":raise ValueError("Not a PNG")
                data=response.read(1_000_001)
            if len(data)>1_000_000 or not data.startswith(b"\x89PNG\r\n\x1a\n"):raise ValueError("Invalid PNG")
            fd,tmp=tempfile.mkstemp(prefix=".emblem-",dir=EMBLEM_DIR)
            with os.fdopen(fd,"wb") as f:f.write(data)
            os.chmod(tmp,0o644);os.replace(tmp,path);tmp=None
            p["emblem_url"]="/assets/platoon-emblems/"+path.name
            retry_marker.unlink(missing_ok=True)
        except Exception as exc:
            retry_marker.touch()
            print("Emblem cache failed for",p["id"],type(exc).__name__,flush=True)
        finally:
            if tmp and os.path.exists(tmp):os.unlink(tmp)



def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
    with engine.connect() as c:
        c.execute(text('SET TRANSACTION READ ONLY'))
        c.execute(text("SET LOCAL statement_timeout='10000ms'"))
        platoons=[dict(r) for r in c.execute(text('SELECT platoon_id::text AS id,name,tag,official_member_count,battlelog_created_at::text AS created_at,emblem_path,website_url,last_success_at::text AS last_success_at FROM platoons ORDER BY name')).mappings()]
        for p in platoons:
            members=[dict(r) for r in c.execute(text('''SELECT a.battlelog_account_id::text AS account_id,a.account_name,a.role,
              COALESCE(json_agg(json_build_object('persona_id',x.persona_id::text,'persona_name',x.persona_name,'platform',x.platform_family,'platform_code',x.battlelog_platform_code,'soldier_id',s.soldier_id::text) ORDER BY x.platform_family,x.persona_name) FILTER (WHERE x.persona_id IS NOT NULL),'[]'::json) AS personas
              FROM platoon_roster_accounts a
              LEFT JOIN platoon_roster_personas x ON x.platoon_id=a.platoon_id AND x.battlelog_account_id=a.battlelog_account_id AND x.is_current
              LEFT JOIN soldiers s ON s.persona_id=x.persona_id AND s.platform=CASE x.battlelog_platform_code WHEN 1 THEN 'pc' WHEN 32 THEN 'ps4' WHEN 64 THEN 'xboxone' ELSE 'unsupported' END
              WHERE a.platoon_id=:pid AND a.is_current
              GROUP BY a.battlelog_account_id,a.account_name,a.role
              ORDER BY CASE a.role WHEN 'founder' THEN 0 WHEN 'leader' THEN 1 ELSE 2 END,a.account_name NULLS LAST
              LIMIT 250'''),{'pid':int(p['id'])}).mappings()]
            # Public roster: retain only accounts with supported-platform personas.
            supported={1,32,64}
            for m in members:
                m['personas']=[x for x in m['personas'] if int(x['platform_code']) in supported]
            members=[m for m in members if m['personas']]
            p['members']=members
            p['visible_member_count']=len(members)
            # Snapshot of current lifetime soldier statistics, one row per supported persona.
            stats=[dict(r) for r in c.execute(text("""SELECT DISTINCT ON (s.soldier_id)
              s.soldier_id::text AS soldier_id,d.kills,d.deaths,d.time_played_seconds,d.total_score,
              d.source_fetched_at::text AS stats_fetched_at
              FROM platoon_roster_personas x
              JOIN platoon_roster_accounts a ON a.platoon_id=x.platoon_id AND a.battlelog_account_id=x.battlelog_account_id AND a.is_current
              JOIN soldiers s ON s.persona_id=x.persona_id AND s.platform=CASE x.battlelog_platform_code WHEN 1 THEN 'pc' WHEN 32 THEN 'ps4' WHEN 64 THEN 'xboxone' END
              JOIN detailed_stats_current d ON d.soldier_id=s.soldier_id
              WHERE x.platoon_id=:pid AND x.is_current AND x.battlelog_platform_code IN (1,32,64)
              ORDER BY s.soldier_id,d.source_fetched_at DESC"""),{'pid':int(p['id'])}).mappings()]
            p['soldier_stats']={r.pop('soldier_id'):r for r in stats}
            p['supported_soldier_count']=len({str(x['persona_id'])+':'+str(x['platform_code']) for m in members for x in m['personas']})

        active_links=[dict(r) for r in c.execute(text("""SELECT s.persona_id::text AS persona_id,s.platform,d.linked_platoon_id::text AS platoon_id,d.last_checked_at::text AS observed_at FROM platoon_soldier_discovery d JOIN soldiers s ON s.soldier_id=d.soldier_id WHERE d.linked_platoon_id IS NOT NULL AND d.last_checked_at IS NOT NULL""")).mappings()]
    cache_emblems(platoons)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.platoons-',suffix='.json',dir=args.output.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump({'platoons':platoons,'membership_note':'Official Battlelog accounts are confirmed roster members; associated BF4 personas are not independently verified soldier memberships.','soldier_page_platoon_links':active_links},f,ensure_ascii=False,default=str)
        os.chmod(tmp,0o644)
        os.replace(tmp,args.output)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print('Published',len(platoons),'platoons',sum(len(p['members']) for p in platoons),'accounts')

if __name__=='__main__':main()
