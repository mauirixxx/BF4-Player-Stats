#!/usr/bin/env python3
"""Discover BF4 weapon showcase renders from wiki API image lists, validating filename AND content."""
import csv,hashlib,json,re,requests,concurrent.futures,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'site/assets/equipment';OUT.mkdir(exist_ok=True,parents=True)
manifest=ROOT/'docs/catalog/equipment-artwork-manifest.json';doc=json.loads(manifest.read_text());assets=doc['assets'];existing={(x['kind'],x['id'],x.get('role','')) for x in assets}
rows=[r for r in csv.DictReader((ROOT/'docs/catalog/equipment-name-inventory.csv').open()) if r['kind']=='weapon']
manual={'AK 5C':'Bf4_ak5c.png','93R':'Bf4_m93r.png','AK-12':'Bf4_ak12.png','AN-94':'BF4_AN94.png','AS VAL':'BF4_asval.png','M416':'Bf4_m416.png'}
# Match case-insensitive normalized names only; never attach a different weapon's render.
def norm(s):return re.sub('[^a-z0-9]','',s.lower())
def url(n):
 h=hashlib.md5(n.encode()).hexdigest();return f'https://static.wikia.nocookie.net/battlefield/images/{h[0]}/{h[:2]}/{n}/revision/latest'
def candidate(fn,name):
 f=fn.removeprefix('File:');base=f.rsplit('.',1)[0];low=base.lower();target=norm(name)
 if not f.lower().endswith(('.png','.webp')):return -1
 if any(b in low for b in ['hud','dog tag','dogtag','sight','held','sprint','model','icon','battlefield_3','bf3_','irl','master','-1','-2','-3','-4']):return -1
 if not ('bf4' in low or 'battlefield_4' in low):return -1
 stem=norm(re.sub('(?i)battlefield[_ -]?4|bf4','',base))
 if stem!=target:return -1
 return 10 if low.startswith(('bf4_','bf4 ')) else 5
def query_page(title):
 try:
  p={'action':'query','titles':title,'prop':'images','imlimit':'max','format':'json'}
  j=requests.get('https://battlefield.fandom.com/api.php',params=p,timeout=12).json();return [x['title'].removeprefix('File:') for x in next(iter(j['query']['pages'].values())).get('images',[])]
 except Exception:return []
def retrieve(fn):
 try:
  r=requests.get(url(fn),timeout=8);assert r.status_code==200 and r.headers.get('Content-Type','').startswith('image/')
  with tempfile.NamedTemporaryFile() as f:
   f.write(r.content);f.flush();p=subprocess.run(['identify','-ping','-format','%m %w %h',f.name],capture_output=True,text=True)
  fmt,w,h=p.stdout.split();w=int(w);h=int(h)
  if w<200 or h<70 or w/h<1.3:return None
  return r.content,fmt,w,h
 except Exception:return None
def scan(r):
 name=r['proposed_label'] or r['current_label'];id_=int(r['catalog_id']);key=('weapon',id_,'fancy')
 if key in existing:return None
 guesses=[manual[name]] if name in manual else []
 variants=[name,name.replace(' ','_'),name.replace(' ','-')]
 for v in variants:guesses.extend(['Bf4_'+v+'.png','BF4_'+v+'.png','BF4_'+v.replace('-','')+'.png'])
 pages=[name,name.replace(' ','_'),name.replace(' ','_')+'/Battlefield_4']
 for page in pages:
  files=query_page(page)
  guesses.extend(sorted(files,key=lambda x:candidate(x,name),reverse=True)[:8] if files else [])
  if any(candidate(f,name)>0 for f in files):break
 for fn in dict.fromkeys(guesses):
  if fn not in manual.values() and candidate(fn,name)<0:continue
  found=retrieve(fn)
  if not found:continue
  data,fmt,w,h=found;path=f'weapon-{id_}-fancy.{fmt.lower()}';(OUT/path).write_bytes(data)
  return {'kind':'weapon','id':id_,'name':name,'role':'fancy','local':'/assets/equipment/'+path,'source':url(fn),'filename':fn,'width':w,'height':h,'format':fmt}
 return None
start=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
 for result in ex.map(scan,rows):
  if result:assets.append(result);print('FOUND',result['id'],result['name'],result['filename'],flush=True)
manifest.write_text(json.dumps(doc,indent=2)+'\n');print('COMPLETE',sum(x['kind']=='weapon' and x.get('role')=='fancy' for x in assets),'of',len(rows),'seconds',round(time.monotonic()-start,1),flush=True)
