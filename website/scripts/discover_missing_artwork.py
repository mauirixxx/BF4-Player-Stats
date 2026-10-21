#!/usr/bin/env python3
"""Read-only discovery of missing artwork. Never imports unreviewed matches or alters manifest."""
import csv,json,re,requests,concurrent.futures,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
rows=list(csv.DictReader((ROOT/'docs/catalog/equipment-name-inventory.csv').open()))
assets=json.loads((ROOT/'docs/catalog/equipment-artwork-manifest.json').read_text())['assets']
covered={(a['kind'],a['raw_key'],a['role']) for a in assets}
s=requests.Session();s.headers['User-Agent']='BF4PlayerStats-ArtCatalog/1.0 (community project)'
def norm(t):return re.sub('[^a-z0-9]','',t.lower())
def get_page(title):
 try:
  p={'action':'query','titles':title,'prop':'images','imlimit':'max','format':'json'}
  j=s.get('https://battlefield.fandom.com/api.php',params=p,timeout=12).json()
  return [x['title'].removeprefix('File:') for x in next(iter(j['query']['pages'].values())).get('images',[])]
 except Exception:return []
def rank(filename,label,role):
 f=filename.rsplit('.',1)[0];low=f.lower();n=norm(label);stem=norm(re.sub('(?i)battlefield[_ -]?4|bf4','',f));
 if not filename.lower().endswith(('.png','.webp')):return 0
 if role=='hud':return 90 if (('battlefield_4_' in low or 'bf4_' in low) and 'hud' in low and 'icon' in low and n in norm(f)) else 0
 if any(t in low for t in ['hud','icon','screenshot','gameplay','dogtag','dog_tag','dog tag','battlefield_3','bf3_','battlefield 3','bf2 ','battlefield 6']):return 0
 if stem==n and ('bf4' in low or 'battlefield_4' in low):return 95
 if ('fancy' in low or 'model' in low) and n in stem:return 80
 if ('bf4' in low or 'battlefield_4' in low) and n in stem:return 65
 return 0
def scan(r):
 kind=r['kind'];key=r['raw_key'];label=r['proposed_label'];missing=[role for role in ('fancy','hud') if (kind,key,role) not in covered]
 if not missing:return None
 # A short set of page variants, no guessed image URLs or ID matching.
 variants=[label,label.replace(' ','_'),label.replace(' ','_')+'/Battlefield_4']
 if kind=='vehicle':variants.append(label.split(' ')[0])
 files=[]
 for title in dict.fromkeys(variants):
  files.extend(get_page(title))
 matches={role:sorted(((rank(f,label,role),f) for f in set(files)),reverse=True)[:3] for role in missing}
 matches={k:[{'score':score,'filename':f} for score,f in v if score>=65] for k,v in matches.items()}
 if not any(matches.values()):return None
 return {'kind':kind,'label':label,'raw_key':key,'candidates':matches}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
 results=[x for x in ex.map(scan,rows) if x]
out=ROOT/'docs/catalog/equipment-artwork-discovery-candidates.json';out.write_text(json.dumps({'note':'Discovery only: filenames are NOT image-content verified and MUST NOT be auto-deployed','candidates':results},indent=2)+'\n')
print('catalog',len(rows),'candidates',len(results),'fancy',sum(bool(x['candidates'].get('fancy')) for x in results),'hud',sum(bool(x['candidates'].get('hud')) for x in results),flush=True)
for x in results:print(x['kind'],x['label'],[(role,[(v['score'],v['filename']) for v in vals]) for role,vals in x['candidates'].items() if vals],flush=True)
