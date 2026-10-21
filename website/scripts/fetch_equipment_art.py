#!/usr/bin/env python3
"""Conservative Fandom image discovery: verified images only, no guessed attribution."""
import csv,hashlib,io,json,re,concurrent.futures,time
from pathlib import Path
import requests
from subprocess import run
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'site/assets/equipment';OUT.mkdir(parents=True,exist_ok=True)
rows=list(csv.DictReader((ROOT/'docs/catalog/equipment-name-inventory.csv').open()))
from collections import OrderedDict
candidates=OrderedDict()
for r in rows:
 if r['kind']!='weapon':continue
 name=r['proposed_label'] or r['current_label'];variants=[name,name.replace(' ','_'),name.replace('-',''),name.replace(' ','').replace('-','')]
 filenames=[]
 for v in variants:
  filenames.extend([f'Battlefield_4_{v}_HUD_Icon.png',f'Battlefield_4_{v}_HUD_icon.png',f'BF4_{v}_HUD_Icon.png'])
 candidates[int(r['catalog_id'])]=(r,list(dict.fromkeys(filenames)))
# Explicit user-supplied sources; vehicle showcase only for now.
explicit=[('weapon',None,'Battlefield_4_AK_5C_HUD_Icon.png','AK 5C'),('vehicle',45,'Ah1z_fancy@2x.png','AH-1Z Viper')]
for kind,id_,fn,name in explicit:
 if id_ is None:
  for id_,(r,files) in candidates.items():
   if r['proposed_label']=='AK 5C':files.insert(0,fn);break

def url(name):
 h=hashlib.md5(name.encode()).hexdigest();return f'https://static.wikia.nocookie.net/battlefield/images/{h[0]}/{h[:2]}/{name}/revision/latest'
def get(name):
 try:
  res=requests.get(url(name),timeout=7,headers={'User-Agent':'BF4PlayerStats-Community-Art-Catalog/1.0'});
  if res.status_code!=200 or not res.headers.get('Content-Type','').startswith('image/') or len(res.content)<400:return None
  from tempfile import NamedTemporaryFile
  with NamedTemporaryFile(suffix='.img') as f:
   f.write(res.content);f.flush();p=run(['identify','-ping','-format','%m %w %h',f.name],capture_output=True,text=True)
  if p.returncode:return None
  fmt,w,h=p.stdout.split();w=int(w);h=int(h)
  if w<60 or h<20:return None
  return res.content,fmt,w,h
 except Exception:return None

records=[];start=time.monotonic()
def scan(t):
 id_,r,files=t
 for fn in files:
  found=get(fn)
  if found:
   data,fmt,w,h=found;ext={'WEBP':'webp','PNG':'png','JPEG':'jpg','GIF':'gif'}.get(fmt,'img');path=f'{id_}.{ext}';(OUT/path).write_bytes(data)
   return {'kind':'weapon','id':id_,'name':r['proposed_label'],'local':'/assets/equipment/'+path,'source':url(fn),'filename':fn,'width':w,'height':h,'format':fmt}
 return None
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
 for item in ex.map(scan,((id_,r,files) for id_,(r,files) in candidates.items())):
  if item:records.append(item);print('FOUND',item['id'],item['name'],item['filename'],flush=True)
for kind,id_,fn,name in explicit:
 if kind=='vehicle':
  found=get(fn)
  if found:
   data,fmt,w,h=found;ext=fmt.lower();path=f'vehicle-{id_}-fancy.{ext}';(OUT/path).write_bytes(data);records.append({'kind':kind,'id':id_,'name':name,'local':'/assets/equipment/'+path,'source':url(fn),'filename':fn,'width':w,'height':h,'format':fmt});print('FOUND vehicle',name,flush=True)
(ROOT/'docs/catalog/equipment-artwork-manifest.json').write_text(json.dumps({'notes':'Only successfully retrieved and image-validated files; game artwork copyright EA/DICE. File-level fair-use analysis remains site operator responsibility.','assets':records},indent=2)+'\n')
print('DONE',len(records),'of',len(candidates),'weapon candidates; seconds',round(time.monotonic()-start,1),flush=True)
