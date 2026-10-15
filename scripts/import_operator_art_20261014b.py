#!/usr/bin/env python3
"""Import operator-curated BF4 Wiki artwork; stable raw keys and exact Wiki file titles."""
import csv,json,requests,subprocess,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ROWS={(r['kind'],r['proposed_label']):r for r in csv.DictReader((ROOT/'docs/catalog/equipment-name-inventory.csv').open())}
ITEMS=[tuple(line.split('|')) for line in "vehicle|Su-50|BF4_su50.png\nvehicle|F-35|BF4_f35.png\nvehicle|Type 95 AA|BF4_Type95aa.png\nvehicle|LAV-AD|BF4_lav-ad.png\nvehicle|AH-6 Little Bird|BF4_ah6.png\nvehicle|ZBD-09|Zbd09_fancy.png\nvehicle|Type 99 MBT|BF4_type99mbt.png\nvehicle|Z-9 Haitun|BF4_z9haitun.png\nvehicle|LYT2021|BF4_lyt2021.png\nvehicle|M220 TOW Launcher|BF4TOW.png\nvehicle|SU-39|Su25_fancy@2x.png\nvehicle|Q-5 Fantan|Q5_fancy@2x.png\nvehicle|Mi-28 Havoc|BF4_mi28.png\nvehicle|BTR-90|Btr90_fancy.png\nvehicle|Z-11W|BF4_z11.png\nvehicle|T-90A|BF4_t90.png\nvehicle|Pantsir-S1|BF4_Pantsir.png\nvehicle|ACV|BF4_ACV_Battlelog_Icon.png\nvehicle|SNOWMOBILE|BF4_Snowmobile.png\nvehicle|Dirt Bike|BF4_Dirtbike.png\nvehicle|GROWLER ITV|BF4_growler.png\nvehicle|KA-60 Kasatka|BF4_ka60.png\nvehicle|Desert Patrol Vehicle|BF4BL_DPV.png\nvehicle|HJ-8 Launcher|HJ-8_Launcher_-_BF4-Icon.png\nvehicle|BOMBER|BF4_Bomber_Icon.png\nvehicle|SPM-3|BF4_spm3.png\nvehicle|ZFB-05|BF4_zfb05.png\nvehicle|UH-1Y Venom|BF4_venom.png\nvehicle|J-20|BF4_j20.png\nvehicle|M142 (HIMARS)|BF4_himars.png\nvehicle|DV-15 Interceptor|BF4_dv15.png\nvehicle|RCB-90|BF4_rcb90.png\nvehicle|Z-10W|BF4_z10w.png\nvehicle|LAV-25|Lav-25_fancy.png\nvehicle|Skid Loader|Skidloader.png\nvehicle|PWC|BF4_pwc.png\nvehicle|SCHIPUNOV 42|BF4_Sc42.png\nvehicle|HT-95 LEVKOV|BF4_Ht95.png\nvehicle|Quad Bike|BF4_Quad_Bike_Battlelog_Icon.png\nvehicle|VDV Buggy|BF4_vdv.png\nvehicle|MRAP|BF4_mrap.png\nvehicle|RHIB Boat|BF4_rhib.png\nvehicle|Centurion C-RAM|BF4_Centurion.png\nweapon|MTAR-21|Bf4_mtar21.png\nweapon|Phantom Bow|BF4_Phantom.png\nvehicle|Old Cannon|BF4_Old_Cannon_Battlelog_Icon.png\nvehicle|.50 Cal|BF4_50cal.png\nvehicle|RAWR|BF4_rawr.png\nweapon|MBT LAW|BF4_MBTLAW_Prof.png\nvehicle|MAV|BF4_MAV.png\nvehicle|M224 MORTAR|BF4_M224_Mortar.png\nweapon|M18 CLAYMORE|BF4_M18_Claymore.png\nweapon|M2 SLAM|M2_slam_fancy@2x.png\nweapon|M320 FB|BF4_40mmflash.png\nweapon|SA-18 IGLA|Bf4_sa18_igla.png\nweapon|C4 EXPLOSIVE|Bf4_c4.png\nweapon|M15 AT MINE|At_mine_fancy@2x.png\nweapon|FGM-148 JAVELIN|Bf4_fgm148_javelin.png\nweapon|SRAW|Bf4_fgm172_sraw.png\nweapon|SMAW|Bf4_mk153_smaw.png\nweapon|DEFIBRILLATOR|Bf4_defib.png\nweapon|M60-E4|BF4_m60e4.png\nweapon|M60 Ultimate|BF4_M60ULTAdios.png\nweapon|REPAIR TOOL|Bf4_repairtool.png".splitlines()]
assert len(ITEMS)==len(set((a,b) for a,b,c in ITEMS))
manifest=ROOT/'docs/catalog/equipment-artwork-manifest.json'
doc=json.loads(manifest.read_text())
assets=doc['assets']
out=ROOT/'site/assets/equipment';out.mkdir(exist_ok=True,parents=True)
s=requests.Session();s.headers['User-Agent']='BF4PlayerStats-ArtCatalog/1.0 (community project)'
ok=[];failed=[]
for kind,label,filename in ITEMS:
 try:
  row=ROWS[(kind,label)]
  p={'action':'query','titles':'File:'+filename,'prop':'imageinfo','iiprop':'url|size','format':'json'}
  r=s.get('https://battlefield.fandom.com/api.php',params=p,timeout=18);r.raise_for_status()
  page=next(iter(r.json()['query']['pages'].values()))
  info=page['imageinfo'][0];url=info['url']
  r=s.get(url.split('?')[0],timeout=20);r.raise_for_status()
  assert r.headers.get('Content-Type','').startswith('image/'),r.headers.get('Content-Type')
  with tempfile.NamedTemporaryFile() as tmp:
   tmp.write(r.content);tmp.flush()
   info_cmd=subprocess.run(['identify','-ping','-format','%w %h',tmp.name],capture_output=True,text=True,check=True)
   w,h=map(int,info_cmd.stdout.split());assert w>=64 and h>=40
   local='/assets/equipment/'+kind+'-'+row['raw_key']+'-fancy.webp'
   args=['convert',tmp.name]
   if label=='Phantom Bow':args+=['-rotate','-90'];w,h=h,w
   args+=['-quality','92',str(out/local.split('/')[-1])]
   subprocess.run(args,check=True,capture_output=True)
  class Dimensions:pass
  im=Dimensions();im.width=w;im.height=h
  rec={'kind':kind,'name':label,'raw_key':row['raw_key'],'audit_catalog_id':int(row['catalog_id']),'role':'fancy','local':local,'source':url,'filename':filename,'width':im.width,'height':im.height,'format':'WEBP','verification':'Operator-selected exact Wiki filename; decoded image; '+('rotated 90 degrees counterclockwise' if label=='Phantom Bow' else 'preserved orientation')}
  ok.append(rec);print('OK',kind,label,filename,im.width,im.height,flush=True)
 except Exception as e:failed.append((kind,label,filename,str(e)));print('FAIL',kind,label,filename,str(e)[:120],flush=True)
for rec in ok:
 assets[:]=[a for a in assets if not(a['kind']==rec['kind'] and a.get('raw_key')==rec['raw_key'] and a['role']=='fancy')]
 assets.append(rec)
manifest.write_text(json.dumps(doc,indent=2)+'\n')
m={}
for a in assets:
 m.setdefault(a['kind']+'-'+a['raw_key'],{})[a['role']]={'local':a['local'],'source':a['source']}
(ROOT/'site/equipment-artwork.js').write_text('/* Indexed by stable raw equipment key; provenance in docs/catalog/equipment-artwork-manifest.json */\nconst equipmentArtwork='+json.dumps(m,separators=(',',':'))+';\n')
p=ROOT/'site/equipment.html';html=p.read_text()
import re
html=re.sub(r'equipment-artwork\.js\?v=[^"\']+', 'equipment-artwork.js?v=operator-batch-20261014b',html)
p.write_text(html)
print('RESULT',len(ok),'success',len(failed),'failed',len(assets),'manifest records',flush=True)
if failed:sys.exit(2)
