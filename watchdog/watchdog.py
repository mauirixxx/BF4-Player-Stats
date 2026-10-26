#!/usr/bin/env python3
"""BF4PS independent infrastructure watchdog. Python stdlib only."""
import json, os, subprocess, time, urllib.request, urllib.error, pathlib, datetime, shutil, socket, sys

BASE=pathlib.Path(__file__).resolve().parent
CONFIG=json.loads((BASE/'admins.json').read_text())
STATE=pathlib.Path('/var/lib/bf4ps-watchdog/state.json')
BOT_ENV=pathlib.Path('/opt/bf4ps-discord/discord-bot/.env')
NODES=['mak-db-01','mak-db-02','hnl-db-01','kah-db-01','rnt-db-01']
TCP_NODES={'mak-02':'192.168.10.75','mak-03':'192.168.10.73','mak-04':'192.168.10.74','mak-05':'192.168.10.79','hnl-01':'192.168.5.70','hnl-02':'192.168.5.69','hnl-03':'192.168.5.68','kah-01':'192.168.21.70','rnt-01':'192.168.200.47'}
def run(cmd,timeout=8):
 try:
  p=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
  return p.returncode,p.stdout.strip()
 except (OSError,subprocess.TimeoutExpired): return 1,''
def check():
 result={}
 def put(key,ok,detail): result[key]={'ok':bool(ok),'detail':str(detail)[:160]}
 for host in NODES:
  rc,out=run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=3',host,'df -P / | tail -1; systemctl is-active postgresql@16-main; pg_lsclusters | grep "16  main"'],10)
  lines=out.splitlines()
  put('node:'+host,rc==0 and len(lines)>=3,'SSH + PostgreSQL check')
  if rc==0 and len(lines)>=3:
   fields=lines[0].split()
   if len(fields)>=6:
    used=int(fields[4].strip('%')); free=int(fields[3])*1024
    put('disk:'+host,used<80 and free>=5*1024**3,f'{used}% used, {free/1024**3:.1f} GiB free')
   put('postgres:'+host,lines[1]=='active' and 'online' in lines[2],lines[1]+' '+lines[2][-70:])
 for host,addr in TCP_NODES.items():
  try:
   with socket.create_connection((addr,22),timeout=2): ok=True
  except OSError:ok=False
  put('node:'+host,ok,'SSH TCP reachability (port 22)')
 for container in ('bf4ps-distributed-rank-mak01','bf4ps-production-collector','bf4ps-discord-ha-mak','bf4ps-weapon-metrics-sync'):
  rc,out=run(['docker','inspect','-f','{{.State.Running}}',container],4)
  put('container:'+container,rc==0 and out=='true',out or 'not running')
 for unit in ('bf4ps-distributed-rank-worker.service','bf4ps-rank-gc.timer','bf4ps-weapon-metrics-sync.service'):
  rc,out=run(['systemctl','is-active',unit],4)
  put('service:'+unit,rc==0 and out=='active',out)
 rc,http=run(['curl','-L','-s','-o','/dev/null','-w','%{http_code}','--max-time','9','https://bf4playerstats.com/'],12)
 put('website:homepage',rc==0 and http=='200','HTTP '+http if http else 'unreachable')
 usage=shutil.disk_usage('/')
 put('disk:mak-01',usage.used/usage.total<0.8 and usage.free>=5*1024**3,f'{usage.used/usage.total:.0%} used, {usage.free/1024**3:.1f} GiB free')
 return result
def token():
 for line in BOT_ENV.read_text().splitlines():
  if line.startswith('DISCORD_BOT_TOKEN='):return line.split('=',1)[1].strip().strip('"').strip("'")
 raise RuntimeError('Discord bot token unavailable')
def api(method,path,payload=None):
 data=json.dumps(payload).encode() if payload is not None else None
 req=urllib.request.Request('https://discord.com/api/v10'+path,data=data,headers={'Authorization':'Bot '+token(),'Content-Type':'application/json','User-Agent':'BF4PS-Watchdog/1.0'},method=method)
 with urllib.request.urlopen(req,timeout=15) as r:return json.loads(r.read())
def deliver(message):
 destinations=[('channel',CONFIG['alert_channel_id'])]
 for admin in CONFIG['admins']:
  if admin.get('enabled'):
   uid=admin['discord_user_id']
   try:destinations.append(('dm:'+uid,api('POST','/users/@me/channels',{'recipient_id':uid})['id']))
   except Exception as e:print('DM channel unavailable',uid,type(e).__name__,flush=True)
 for name,cid in destinations:
  try:
   api('POST','/channels/'+cid+'/messages',{'content':message,'allowed_mentions':{'parse':[]}})
   print('DELIVERED',name,flush=True)
  except Exception as e:print('DELIVERY FAILED',name,type(e).__name__,flush=True)
def main():
 if '--test' in sys.argv:
  deliver('🧪 **BF4PS infrastructure watchdog TEST** — channel + all configured admin DMs. This is a controlled test, **not an outage**.')
  return
 STATE.parent.mkdir(parents=True,exist_ok=True)
 results=check()
 previous=json.loads(STATE.read_text()) if STATE.exists() else {}
 incidents=previous.get('incidents',{})
 baseline=not STATE.exists()
 for key,val in results.items():
  old=incidents.get(key,{'failures':0,'open':False})
  failures=0 if val['ok'] else old.get('failures',0)+1
  opened=old.get('open',False)
  if not baseline and failures>=3 and not opened:
   deliver('🚨 **BF4PS ALERT** '+key+' — '+val['detail'])
   opened=True
  if opened and val['ok']:
   deliver('✅ **BF4PS RECOVERED** '+key+' — '+val['detail'])
   opened=False
  incidents[key]={'failures':failures,'open':opened,'detail':val['detail']}
 tmp=STATE.with_suffix('.tmp')
 tmp.write_text(json.dumps({'incidents':incidents,'last_check_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
 os.replace(tmp,STATE)
 print('checks',len(results),'healthy',sum(v['ok'] for v in results.values()),'unhealthy',sum(not v['ok'] for v in results.values()),'baseline',baseline)
if __name__=='__main__':main()
