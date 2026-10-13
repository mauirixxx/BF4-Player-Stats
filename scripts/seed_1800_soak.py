"""Freeze and seed an explicit 1,800-new-soldier scratch-only BF4PS soak."""
import argparse, json, os
from pathlib import Path
from sqlalchemy import create_engine, text
from bf4ps.discovery import load_aliases, import_aliases
FRIENDS=("deathdealer7520","blurrr666","yukonsunshine","team-ajax","madman0529","FooeY","mtallicLuis","Grimtorvus","S3AS0NALLY","Ocelot3377")
PLATFORMS=(("PC","pc"),("PS4/5","ps4"),("XBox","xboxone"))
MANIFEST=Path("/root/bf4ps-1800-soak-manifest.json")
def main():
 p=argparse.ArgumentParser();p.add_argument("--execute",action="store_true");a=p.parse_args()
 src=create_engine(os.environ["BF4PS_BF4SW_DATABASE_URL"],connect_args={"options":"-c default_transaction_read_only=on -c statement_timeout=120000"})
 dst=create_engine(os.environ["BF4PS_DATABASE_URL"],pool_pre_ping=True)
 with src.connect() as s,dst.connect() as d:
  assert s.execute(text("select current_database()")).scalar_one()=="bf4_serverwatcher"
  assert d.execute(text("select current_database()")).scalar_one()=="bf4ps_scratch_stage9c_d3"
  assert d.execute(text("select count(*) from soldiers")).scalar_one()==451
  assert d.execute(text("select count(*) from collection_jobs")).scalar_one()==0
  current={(r[0],int(r[1])) for r in d.execute(text("select platform,persona_id from soldiers"))}
  selected=[]; seen=set()
  def add(platform,persona,name):
   key=(platform,int(persona))
   if key in current or key in seen:return False
   selected.append(dict(platform=platform,persona_id=int(persona),name=name));seen.add(key);return True
  for friend in FRIENDS:
   rows=s.execute(text("select persona_id,player_name from bf4_player_aliases where platform='PC' and lower(player_name)=lower(:n) order by last_seen desc"),{"n":friend}).all()
   ids={int(x[0]) for x in rows}
   assert len(ids)==1,(friend,rows)
   assert add("pc",rows[0][0],rows[0][1]),friend
  for source_platform,platform in PLATFORMS:
   needed=600-sum(x["platform"]==platform for x in selected)
   rows=s.execute(text("""SELECT DISTINCT ON (persona_id) persona_id,player_name,last_seen FROM bf4_player_aliases WHERE platform=:p AND persona_id IS NOT NULL ORDER BY persona_id,last_seen DESC"""),{"p":source_platform}).all()
   rows=sorted(rows,key=lambda x:x[2],reverse=True)
   for persona,name,_ in rows:
    if needed==0:break
    if add(platform,persona,name):needed-=1
   assert needed==0,(platform,needed)
  assert len(selected)==1800
  assert {p:sum(x["platform"]==p for x in selected) for p in ("pc","ps4","xboxone")}=={"pc":600,"ps4":600,"xboxone":600}
  print("SELECTED",len(selected),"FRIENDS",len(FRIENDS),"EXISTING",len(current),flush=True)
  if not a.execute:
   print("DRY RUN ONLY; no database changes",flush=True);return
  assert not MANIFEST.exists(),"manifest already exists; refusing reseed"
  for i,row in enumerate(selected,1):
   source_platform=next(sp for sp,dp in PLATFORMS if dp==row["platform"])
   with src.connect() as sc,dst.begin() as dc:
    aliases=load_aliases(sc,persona_id=row["persona_id"],platform=source_platform)
    row["soldier_id"]=int(import_aliases(dc,aliases))
    for resource in ("detailed","weapons","vehicles","profile"):
     dc.execute(text("""INSERT INTO collection_jobs(soldier_id,resource,lane,priority_class,reason,status)
       VALUES (:id,:resource,'background','bootstrap','1800_soak','pending')
       ON CONFLICT(soldier_id,resource) DO NOTHING"""),{"id":row["soldier_id"],"resource":resource})
   if i%100==0:print("SEEDED",i,flush=True)
  with dst.connect() as dc:
   assert dc.execute(text("select count(*) from soldiers")).scalar_one()==2251
   assert dc.execute(text("select count(*) from collection_jobs")).scalar_one()==7200
  MANIFEST.write_text(json.dumps({"name":"bf4ps-1800-20261013","cohort":selected},indent=2)+"\n")
  MANIFEST.chmod(0o600)
  print("COMPLETE",len(selected),"MANIFEST",MANIFEST,flush=True)
if __name__=="__main__":main()
