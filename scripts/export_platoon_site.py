#!/usr/bin/env python3
"""Read-only bounded export for public platoon pages; atomically publish JSON."""
import argparse, json, os, tempfile
from pathlib import Path
from sqlalchemy import create_engine, text


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
    with engine.connect() as c:
        c.execute(text('SET TRANSACTION READ ONLY'))
        c.execute(text("SET LOCAL statement_timeout='10000ms'"))
        platoons=[dict(r) for r in c.execute(text('SELECT platoon_id::text AS id,name,tag,official_member_count,last_success_at::text AS last_success_at FROM platoons ORDER BY name')).mappings()]
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
            p['members']=members
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.platoons-',suffix='.json',dir=args.output.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump({'platoons':platoons,'membership_note':'Official Battlelog accounts are confirmed roster members; associated BF4 personas are not independently verified soldier memberships.'},f,ensure_ascii=False,default=str)
        os.chmod(tmp,0o644)
        os.replace(tmp,args.output)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print('Published',len(platoons),'platoons',sum(len(p['members']) for p in platoons),'accounts')

if __name__=='__main__':main()
