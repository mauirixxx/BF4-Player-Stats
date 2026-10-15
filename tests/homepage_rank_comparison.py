"""Compare live API top ranks with legacy JSON export without changing production."""
import json,os,sys,time
from pathlib import Path
from sqlalchemy import create_engine,text
sys.path.insert(0,'api')
from general_leaderboard import query_page
p=Path('/var/www/bf4playerstats.com/temp-stats-data.json')
legacy=json.loads(p.read_bytes())
print('snapshot',legacy.get('updated'),'soldiers',len(legacy['soldiers']))
with create_engine(os.environ['BF4PS_DATABASE_URL']).connect() as conn:
 conn.execute(text('SET TRANSACTION READ ONLY'))
 conn.execute(text("SET LOCAL statement_timeout = '5000ms'"))
 for metric in ('kills','wins','total_score','time_played_seconds'):
  result=query_page(conn,metric,'all',page_size=50)
  eligible=[x for x in legacy['soldiers'] if x.get('detailed_state')=='success' and x.get(metric) is not None]
  eligible.sort(key=lambda x:(-float(x[metric]),x['soldier_id']))
  old=[int(x['soldier_id']) for x in eligible[:50]]
  new=[int(x['soldier_id']) for x in result['rows']]
  match=sum(a==b for a,b in zip(old,new))
  print(metric,'legacy',len(eligible),'live',result['population'],'same_positions',match,'of',len(new),'top',old[:2],new[:2])
