"""Scratch-only HTTP smoke: test-loaded module changes DB name guard in memory only."""
import os,sys,threading,json,urllib.request,importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
base=Path('/opt/bf4ps-general-rank-scratch/website/api')
sys.path.insert(0,str(base))
src=(base/'leaderboard_api.py').read_text()
assert src.count("!='bf4_playerstats'")>=1
# Test-only source transformation, never written to website files.
src=src.replace("!='bf4_playerstats'","!='bf4ps_rank_scratch'")
namespace={'__name__':'scratch_http_api','__file__':str(base/'leaderboard_api.py')}
exec(compile(src,str(base/'leaderboard_api.py'),'exec'),namespace)
server=ThreadingHTTPServer(('127.0.0.1',0),namespace['Handler'])
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    url='http://127.0.0.1:%s/general-leaderboard?metric=kills&platform=all&page=1&page_size=10'%server.server_port
    def get(suffix=''):
        with urllib.request.urlopen(url+suffix,timeout=15) as response:
            assert response.status==200
            return json.load(response)
    os.environ['BF4PS_GENERAL_RANK_SNAPSHOT_READS']='1'
    a=get()
    assert a['rank_source']=='published_snapshot' and a['generation_id']==4 and len(a['rows'])==10
    print('PASS HTTP snapshot',a['generation_id'],a['population'],len(a['rows']),flush=True)
    b=get('&search=bench_999')
    assert b['rank_source']=='published_snapshot'
    print('PASS HTTP indexed search',b['filtered_count'],flush=True)
    os.environ['BF4PS_GENERAL_RANK_SNAPSHOT_READS']='0'
    c=get()
    assert c['rank_source']=='live' and c['population']==a['population']
    print('PASS HTTP legacy fallback when disabled',len(c['rows']),flush=True)
finally:
    server.shutdown();server.server_close()
