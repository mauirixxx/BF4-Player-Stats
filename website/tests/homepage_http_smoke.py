"""Run isolated read-only API HTTP smoke tests; never touch public service."""
import json,os,subprocess,time,urllib.request,urllib.error
from pathlib import Path

BASE='http://127.0.0.1:18877'
env=os.environ.copy()
env['BF4PS_API_PORT']='18877'
proc=subprocess.Popen(['.venv/bin/python','-u','api/leaderboard_api.py'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
def get(path):
    with urllib.request.urlopen(BASE+path,timeout=10) as response:
        return json.load(response)
try:
    for _ in range(30):
        try:
            if get('/health')['status']=='ok':break
        except Exception:time.sleep(.15)
    else:raise RuntimeError('API failed to start')
    first=get('/general-leaderboard?metric=kills&platform=all&page=1&page_size=50')
    assert len(first['rows'])==50
    assert first['rows'][0]['position']==1
    assert first['rows'][0]['rank']==1
    second=get('/general-leaderboard?metric=kills&platform=all&page=2&page_size=50')
    assert second['rows'][0]['position']==51
    assert second['rows'][0]['soldier_id']!=first['rows'][0]['soldier_id']
    target=second['rows'][0]
    located=get('/general-leaderboard?metric=kills&platform=all&page=1&page_size=1&search='+str(target['persona_id']))
    assert any(x['soldier_id']==target['soldier_id'] for x in located['rows'])
    assert (located['rows'][0]['position']-1)//50==1
    search=get('/global-soldier-search?q=FooeY')
    assert isinstance(search['rows'],list)
    try:
        get('/general-leaderboard?metric=drop&platform=all')
        raise AssertionError('Invalid metric accepted')
    except urllib.error.HTTPError as e:assert e.code==400
    print('PASS isolated HTTP: health, page1, page2, stable deep-link position, global search, invalid metric')
    print('population',first['population'],'first_page_rows',len(first['rows']),'page2_first_position',second['rows'][0]['position'],'FooeY_matches',len(search['rows']))
finally:
    proc.terminate()
    try:proc.communicate(timeout=3)
    except subprocess.TimeoutExpired:proc.kill();proc.communicate()
