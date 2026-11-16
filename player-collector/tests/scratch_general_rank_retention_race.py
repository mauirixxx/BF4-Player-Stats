"""Scratch-only: prove an old published generation can vanish mid-request."""
import os
from sqlalchemy import create_engine,text
from bf4ps.general_rank_reader import query_page
engine=create_engine(os.environ['BF4PS_DATABASE_URL'])
with engine.begin() as w:
    original=w.execute(text("""SELECT generation_id FROM general_rank_published
        WHERE metric='kills' AND platform='all'""")).scalar_one()
    temp=w.execute(text("""INSERT INTO general_rank_generations(metric,platform,population,completed_at)
        VALUES ('kills','all',0,now()) RETURNING generation_id""")).scalar_one()
    w.execute(text("""INSERT INTO general_rank_rows
        (generation_id,position,soldier_id,value,rank,division,hours_source_seconds)
        SELECT :g,1,soldier_id,value,1,1,hours_source_seconds
        FROM general_rank_rows WHERE generation_id=:old AND position=1"""),{'g':temp,'old':original})
    w.execute(text("UPDATE general_rank_generations SET population=1 WHERE generation_id=:g"),{'g':temp})
    w.execute(text("""UPDATE general_rank_published SET generation_id=:g,published_at=now()
        WHERE metric='kills' AND platform='all'"""),{'g':temp})
print('temporary published',temp,flush=True)
try:
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as reader:
        reader.execute(text('SET TRANSACTION READ ONLY'))
        seen=reader.execute(text("""SELECT generation_id FROM general_rank_published
            WHERE metric='kills' AND platform='all'""")).scalar_one()
        assert seen==temp
        with engine.begin() as w:
            w.execute(text("""UPDATE general_rank_published SET generation_id=:g,published_at=now()
                WHERE metric='kills' AND platform='all'"""),{'g':original})
            w.execute(text("DELETE FROM general_rank_generations WHERE generation_id=:g"),{'g':temp})
        after=query_page(reader,'kills','all')
        print('reader generation after deletion',after['generation_id'] if after else None,flush=True)
        print('rows after deletion',len(after['rows']) if after else None,flush=True)
        assert after and after['generation_id']==temp and len(after['rows'])==1
        print('PASS reader retained actual ranking row after deletion',flush=True)
        reader.rollback()
finally:
    with engine.begin() as w:
        w.execute(text("""UPDATE general_rank_published SET generation_id=:g,published_at=now()
            WHERE metric='kills' AND platform='all'"""),{'g':original})
        w.execute(text("DELETE FROM general_rank_generations WHERE generation_id=:g"),{'g':temp})
print('restored',original,flush=True)