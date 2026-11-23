"""Sequential BF4PS general-rank refresh with safe retention of current pointers."""
import os,pwd,subprocess,sys,time
from pathlib import Path
ROOT='/opt/bf4ps-general-rank-0026/player-collector'
VENV='/opt/bf4ps-general-rank-0026/.venv/bin/python'
sys.path.insert(0,ROOT)
from bf4ps.general_rank_publisher import METRICS,PLATFORMS
p=pwd.getpwnam('postgres')
ENV=dict(os.environ, BF4PS_DATABASE_URL='postgresql+psycopg://postgres@/bf4_playerstats?host=/var/run/postgresql', PYTHONPATH=ROOT)
def as_pg():
    os.setgroups([])
    os.setgid(p.pw_gid)
    os.setuid(p.pw_uid)
def prune():
    # Never delete a published generation; keep one prior generation per scope for rollback.
    sql="""WITH numbered AS (
      SELECT generation_id, row_number() OVER (PARTITION BY metric,platform ORDER BY generation_id DESC) AS rn
      FROM general_rank_generations
    ), obsolete AS (
      SELECT n.generation_id FROM numbered n
      WHERE n.rn>2 AND NOT EXISTS (
        SELECT 1 FROM general_rank_published p WHERE p.generation_id=n.generation_id
      )
      ORDER BY n.generation_id LIMIT 2
    )
    DELETE FROM general_rank_generations g USING obsolete o WHERE g.generation_id=o.generation_id"""
    r=subprocess.run(['/usr/bin/psql','-v','ON_ERROR_STOP=1','-d','bf4_playerstats','-c',sql],preexec_fn=as_pg,capture_output=True,text=True)
    if r.returncode: print('RETENTION ERROR',r.stderr,flush=True)
    else: print('RETENTION',r.stdout.strip(),flush=True)
def main():
    print('Starting general rank refresh',flush=True)
    failed=[]
    for metric in METRICS:
        for platform in PLATFORMS:
            started=time.monotonic()
            r=subprocess.run([VENV,'-m','bf4ps.general_rank_publisher','--metric',metric,'--platform',platform,'--execute'],cwd=ROOT,env=ENV,preexec_fn=as_pg,capture_output=True,text=True)
            print(metric,platform,'seconds',round(time.monotonic()-started,2),'exit',r.returncode,r.stdout.strip(),r.stderr[-500:].strip(),flush=True)
            if r.returncode: failed.append(metric+'/'+platform)
            else: prune()
            time.sleep(3)
    print('DONE failures',failed,flush=True)
    return 1 if failed else 0
if __name__=='__main__':sys.exit(main())
