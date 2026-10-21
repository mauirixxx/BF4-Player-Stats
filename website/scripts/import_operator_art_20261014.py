#!/usr/bin/env python3
"""Import explicitly operator-selected Battlefield Wiki files, matched by audited raw keys."""
import csv,json,requests,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
# Kind, audited label, exact Wiki filename, image role.
ITEMS=[
('weapon','M16A4','Bf4_m16a4.png','fancy'),('weapon','ACE 23','Bf4_galil_ace23.png','fancy'),
('weapon','AEK-971','Bf4_aek971.png','fancy'),('weapon','AEK-971','Battlefield_4_AEK-971_HUD_Icon.png','hud'),
('weapon','AK-12','Bf4_ak12.png','fancy'),('weapon','AK-12','Battlefield_4_AK-12_HUD_Icon.png','hud'),
('weapon','AR160','BF4_AR-160.png','fancy'),('weapon','AUG A3','Bf4_steyraug.png','fancy'),
('vehicle','UCAV','BF4_UCAV.png','fancy'),('vehicle','SUAV','BF4_SUAV.png','fancy'),
('vehicle','EOD BOT','BF4_EOD_Bot.png','fancy'),('weapon','BULLDOG','Bulldog_fancy.png','fancy'),
('weapon','CZ-805','Bf4_cz805.png','fancy'),('weapon','F2000','F2000_fancy.png','fancy'),
('weapon','FAMAS','Bf4_famas.png','fancy'),('weapon','L85A2','Bf4_l85a2.png','fancy'),
('weapon','QBZ-95-1','Bf4_qbz951.png','fancy'),('weapon','SAR-21','Bf4_sar21.png','fancy'),
('weapon','SCAR-H','Bf4_scarh.png','fancy'),('vehicle','9K22 Tunguska-M','BF4_Tunguska.png','fancy'),
('vehicle','9M133 Kornet Launcher','BF4KornetLauncher.png','fancy'),('vehicle','A-10 Warthog','BF4_a10.png','fancy'),
('vehicle','AAV-7A1 AMTRAC','Aav_fancy@2x.png','fancy'),('vehicle','AC-130 Gunship','BF4_ac130.png','fancy'),
('vehicle','MAV','BF4_MAV.png','fancy'),('vehicle','M1 Abrams','BF4_abrams.png','fancy'),
('vehicle','LD-2000 AA','BF4_Ld-2000.png','fancy')]
rows={(r['kind'],r['proposed_label']):r for r in csv.DictReader((ROOT/'docs/catalog/equipment-name-inventory.csv').open())}
manifest=ROOT/'docs/catalog/equipment-artwork-manifest.json';doc=json.loads(manifest.read_text());assets=doc['assets'];dest=ROOT/'site/assets/equipment';dest.mkdir(parents=True,exist_ok=True)
for kind,label,filename,role in ITEMS:assert (kind,label) in rows,(kind,label)
# Wiki API resolves canonical source URLs without guessing filename hashes.
session=requests.Session();session.headers.update({'User-Agent':'BF4PlayerStats-ArtCatalog/1.0 (community noncommercial project)'})
verified=[];fail=[]
for kind,label,filename,role in ITEMS:
 try:
  p={'action':'query','titles':'File:'+filename,'prop':'imageinfo','iiprop':'url|size','format':'json'}
  result=session.get('https://battlefield.fandom.com/api.php',params=p,timeout=15);result.raise_for_status();page=next(iter(result.json()['query']['pages'].values()));info=page['imageinfo'][0];url=info['url']
  response=session.get(url.split('?')[0],timeout=15);response.raise_for_status()
  assert response.headers.get('Content-Type','').startswith('image/'),(filename,response.headers.get('Content-Type'))
  with tempfile.NamedTemporaryFile() as f:
   f.write(response.content);f.flush();q=subprocess.run(['identify','-ping','-format','%m %w %h',f.name],capture_output=True,text=True,check=True)
  fmt,w,h=q.stdout.split();w=int(w);h=int(h);assert w>=80 and h>=35,(filename,w,h)
  row=rows[(kind,label)];raw=row['raw_key'];ext={'WEBP':'webp','PNG':'png','JPEG':'jpg'}.get(fmt,fmt.lower());local=f'/assets/equipment/{kind}-{raw}-{role}.{ext}'
  (dest/local.rsplit('/',1)[1]).write_bytes(response.content)
  record={'kind':kind,'name':label,'raw_key':raw,'audit_catalog_id':int(row['catalog_id']),'role':role,'local':local,'source':url,'filename':filename,'width':w,'height':h,'format':fmt,'verification':'Operator-supplied Wiki file; image decoded and dimensions verified'}
  verified.append(record);print('OK',kind,label,role,filename,w,h,flush=True)
 except Exception as exc:fail.append((kind,label,filename,str(exc)));print('FAIL',label,filename,str(exc)[:110],flush=True)
# Replace exact role+raw identity only after all successful files are downloaded.
for rec in verified:assets[:]=[a for a in assets if not(a['kind']==rec['kind'] and a.get('raw_key')==rec['raw_key'] and a.get('role')==rec['role'])];assets.append(rec)
manifest.write_text(json.dumps(doc,indent=2)+'\n')
print('RESULT',len(verified),'success',len(fail),'fail',flush=True)
