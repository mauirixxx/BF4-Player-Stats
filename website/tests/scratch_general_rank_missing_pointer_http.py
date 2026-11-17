"""Scratch-only HTTP no-pointer fallback; restores original pointer in finally."""
import os,sys,json,threading,urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from sqlalchemy import create_engine,text
base=Path('/opt/bf4ps-general-rank-scratch/website/api')
sys.path.insert(0,str(base))
src=(base/'leaderboard_api.py').read_text()
assert src.count("!='bf4_playerstats'")>=1
src=src.replace("!='bf4_playerstats'","!='bf4ps_rank_scratch'")
ns={'__name__':'scratch_http_fallback','__file__':str(base/'leaderboard_api.py')}
exec(compile(src,str(base/'leaderboard_api.py'),'exec'),ns)
engine=create_engine(os.environ['BF4PS_DATABASE_URL'])
with engine.connect() as c:
 assert c.execute(text('select current_database()')).scalar_one()=='bf4ps_rank_scratch'
 assert c.execute(text('select version_num from alembic_version')).scalar_one()=='0026_general_rank_snapshots'
 scope=c.execute(text("SELECT generation_id,published_at FROM general_rank_published WHERE metric='kills' AND platform='all'")).one()
server=ThreadingHTTPServer(('127.0.0.1',0),ns['Handler'])
threading.Thread(target=server.serve_forever,daemon=True).start()
os.environ['BF4PS_GENERAL_RANK_SNAPSHOT_READS']='1'
url=f'http://127.0.0.1:{server.server_port}/general-leaderboard?metric=kills&platform=all&page_size=10'
try:
 with urllib.request.urlopen(url,timeout=15) as r: before=json.load(r)
 assert before['rank_source']=='published_snapshot'
 with engine.begin() as c:
  c.execute(text("DELETE FROM general_rank_published WHERE metric='kills' AND platform='all'"))
 with urllib.request.urlopen(url,timeout=15) as r: missing=json.load(r)
 assert missing['rank_source']=='live' and len(missing['rows'])==10,missing
 print('PASS flag ON missing pointer uses live reader',missing['population'],flush=True)
finally:
 with engine.begin() as c:
  c.execute(text("""INSERT INTO general_rank_published(metric,platform,generation_id,published_at)
    VALUES ('kills','all',:generation,:published)
    ON CONFLICT (metric,platform) DO UPDATE
    SET generation_id=EXCLUDED.generation_id,published_at=EXCLUDED.published_at"""),
    {'generation':scope.generation_id,'published':scope.published_at})
 server.shutdown();server.server_close();engine.dispose()
print('PASS original publication pointer restored',scope.generation_id,flush=True)
