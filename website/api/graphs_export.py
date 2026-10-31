#!/usr/bin/env python3
"""Daily read-only BF4PS trends export; full completion deltas start at first snapshot."""
import json,os,tempfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
from sqlalchemy import create_engine,text
OUT=Path('/var/www/bf4playerstats.com/graphs-data.json')
HISTORY=Path('/var/lib/bf4ps/graphs-snapshots.json')
def main():
 now=datetime.now(timezone.utc); today=now.date(); yesterday=today-timedelta(days=1)
 engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
 with engine.connect() as c:
  c.execute(text('SET TRANSACTION READ ONLY'))
  c.execute(text("SET LOCAL statement_timeout='90000ms'"))
  def daily(table,column):
   sql=f'SELECT ({column} AT TIME ZONE \'UTC\')::date AS day,count(*) AS n FROM public.{table} WHERE {column} IS NOT NULL AND {column} < :cutoff GROUP BY 1 ORDER BY 1'
   return {str(r.day):int(r.n) for r in c.execute(text(sql),{'cutoff':today}).all()}
  soldiers=daily('soldiers','first_seen_at'); platoons=daily('platoons','first_seen_at')
  platform_soldiers={}
  for row in c.execute(text("SELECT (first_seen_at AT TIME ZONE 'UTC')::date AS day, platform, count(*) AS n FROM public.soldiers WHERE first_seen_at IS NOT NULL AND first_seen_at < :cutoff GROUP BY 1,2"),{'cutoff':today}):
   platform_soldiers.setdefault(str(row.day),{})[row.platform]=int(row.n)
  full=int(c.execute(text("SELECT count(*) FROM public.collection_state cs JOIN public.soldiers s ON s.soldier_id=cs.soldier_id WHERE cs.detailed_state='success' AND cs.profile_state='success' AND cs.weapons_state='success' AND cs.vehicles_state='success' AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)" )).scalar_one())
 HISTORY.parent.mkdir(parents=True,exist_ok=True)
 history=json.loads(HISTORY.read_text()) if HISTORY.exists() else {}
 # Current full count is a point-in-time baseline; do not misrepresent it as yesterday's count.
 history[str(today)]={'full_total':full}
 days=sorted(set(soldiers)|set(platoons)|{d for d in history if d < str(today)})
 full_daily={}
 for d in sorted(history):
  previous=(datetime.fromisoformat(d).date()-timedelta(days=1)).isoformat()
  if previous in history: full_daily[d]=max(0,history[d]['full_total']-history[previous]['full_total'])
 payload={'generated_at':now.isoformat(),'timezone':'UTC','note':'Full-stats daily net growth begins with the first recorded snapshot; refreshes and exclusions may affect net growth.','days':[{'date':d,'soldiers':soldiers.get(d,0),'soldiers_by_platform':{p:platform_soldiers.get(d,{}).get(p,0) for p in ('pc','ps4','xboxone')},'platoons':platoons.get(d,0),'full':full_daily.get(d)} for d in days]}
 def publish(path,data):
  fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.graphs-')
  try:
   with os.fdopen(fd,'w') as f:json.dump(data,f,separators=(',',':'))
   os.chmod(tmp,0o644);os.replace(tmp,path)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
 publish(HISTORY,history);publish(OUT,payload)
 print('Published',len(days),'days; full baseline',full)
if __name__=='__main__':main()
