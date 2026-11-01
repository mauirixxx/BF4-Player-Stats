import os,sys
from pathlib import Path
from decimal import Decimal
root=Path('/tmp/bf4ps-compact-final')
sys.path[:0]=[str(root/'player-collector'),str(root/'website/api')]
os.environ['BF4PS_DATABASE_URL']='postgresql+psycopg://postgres@127.0.0.1:55432/bf4ps_ranking_scratch'
os.environ['BF4PS_COMPACT_RANK_READS']='0'
os.environ['BF4PS_PRECOMPUTED_RANK_READS']='0'
import build_compact_rank as builder
import leaderboard_api as legacy
from sqlalchemy import create_engine
from unittest.mock import patch
captures=[]
original=builder.encode_block
def record(rows):
    captures.extend(rows)
    return original(rows)
engine=create_engine(os.environ['BF4PS_DATABASE_URL'])
for kind,item,metric in [('vehicle',2,'kills'),('vehicle',2,'kpm'),('vehicle',47,'kills'),('vehicle',47,'kpm'),('weapon',1,'kills'),('weapon',1,'kpm'),('weapon',1,'accuracy')]:
    captures.clear()
    with patch.object(builder,'encode_block',record),patch.object(sys,'argv',['build_compact_rank.py','--kind',kind,'--item',str(item),'--platform','pc','--metric',metric]):
        builder.main()
    with engine.connect() as conn:
        result=legacy.get_page(conn,kind,'pc',item,1,7,'',0,metric)
    actual=[(int(r[0]),int(r[1]),int(r[2]),None if r[3] is None else Decimal(str(r[3])),None if r[4] is None else Decimal(str(r[4]))) for r in captures]
    expected=[(int(r['soldier_id']),int(r['rank']),int(r['kills']),None if r['kpm'] is None else Decimal(str(r['kpm'])),None if r['accuracy'] is None else Decimal(str(r['accuracy']))) for r in result['rows']]
    assert actual==expected,(kind,item,metric,actual,expected)
    assert result['population']==len(captures)
    print('PARITY PASS',kind,item,metric,'rows',len(actual))
