#!/usr/bin/env python3
"""Loopback-only validated platoon admission. Gateway must enforce CSRF/rate limits."""
import json, os, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from sqlalchemy import create_engine, text

engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
PATH=re.compile(r'^/bf4/platoons/(?:members|view)/([1-9][0-9]{0,18})/?$')
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  if self.path not in ('/submit','/refresh-soldier','/refresh-platoon') or self.headers.get('Content-Type')!='application/json':self.send_error(404);return
  try:
   size=int(self.headers.get('Content-Length','0'))
   if size<1 or size>1024:raise ValueError('Invalid size')
   data=json.loads(self.rfile.read(size))
   if self.path=='/refresh-platoon':
    if (not isinstance(data,dict) or set(data)!={'platoon_id','lan_bypass'}
        or not isinstance(data['platoon_id'],str) or not re.fullmatch(r'[1-9][0-9]{0,18}',data['platoon_id'])
        or type(data['lan_bypass']) is not bool):raise ValueError('Invalid refresh request')
    pid=int(data['platoon_id'])
    with engine.begin() as c:
     c.execute(text("SET LOCAL statement_timeout='5000ms'"))
     result=c.execute(text('SELECT state,retry_after_seconds FROM public.request_platoon_refresh(:pid,:bypass)'),{'pid':pid,'bypass':data['lan_bypass']}).mappings().one()
     state=result['state'];retry=result['retry_after_seconds']
    if state=='not_found':self.reply(404,{'state':state});return
    artwork='pending'
    if state in ('queued','already_queued'):
     try:
      import sys
      sys.path.insert(0,'/opt/bf4ps-website/scripts')
      from pathlib import Path
      from cache_platoon_emblems import emblem_asset,fetch
      from build_platoon_preview_images import render
      from build_platoon_preview_index import build
      root=Path('/var/www/bf4playerstats.com')
      with engine.connect() as c:
       template=c.execute(text('SELECT emblem_path FROM platoons WHERE platoon_id=:pid'),{'pid':pid}).scalar()
      asset=emblem_asset(str(pid),template,root/'assets/platoon-emblems')
      if asset:
       url,path=asset
       # Manual refresh deliberately re-fetches artwork, even when locally cached.
       fetch(url,path)
       dest=root/'assets/platoon-previews'/(path.stem+'-v3.png')
       render(path,dest)
       build(engine,root)
       artwork='ready' if dest.is_file() else 'unavailable'
      else:artwork='no_emblem_url'
     except Exception:
      artwork='retry_scheduled'
    self.reply(200,{'state':state,'retry_after_seconds':retry,'platoon_id':str(pid),'artwork':artwork});return
   if self.path=='/refresh-soldier':
    if not isinstance(data,dict) or set(data)!={'soldier_id'} or not isinstance(data['soldier_id'],int) or isinstance(data['soldier_id'],bool) or data['soldier_id']<=0:raise ValueError('Invalid soldier ID')
    sid=data['soldier_id']
    with engine.begin() as c:
     c.execute(text("SET LOCAL statement_timeout='5000ms'"))
     # Serialize requests per soldier, including simultaneous submissions.
     c.execute(text('SELECT pg_advisory_xact_lock(81405,:sid)'),{'sid':sid})
     soldier=c.execute(text('SELECT soldier_id FROM soldiers WHERE soldier_id=:sid'),{'sid':sid}).first()
     if not soldier:self.reply(404,{'error':'soldier_not_found'});return
     state=c.execute(text('SELECT status,last_checked_at,next_attempt_at FROM platoon_soldier_discovery WHERE soldier_id=:sid FOR UPDATE'),{'sid':sid}).mappings().first()
     if state and state['status']=='running':status='already_running'
     elif state and state['status']=='pending' and state['next_attempt_at'] is not None and state['next_attempt_at'].year<2000:status='already_queued'
     else:
      c.execute(text("""INSERT INTO platoon_soldier_discovery(soldier_id,status,attempts,next_attempt_at,last_error)
       VALUES (:sid,'pending',0,TIMESTAMPTZ '1970-01-01',NULL)
       ON CONFLICT(soldier_id) DO UPDATE SET status='pending',attempts=0,next_attempt_at=TIMESTAMPTZ '1970-01-01',last_error=NULL"""),{'sid':sid})
      status='queued'
    self.reply(200,{'state':status,'soldier_id':sid});return
   url=data['url'];parts=urlsplit(url)
   if not isinstance(url,str) or len(url)>500 or parts.scheme!='https' or parts.netloc!='battlelog.battlefield.com' or parts.query or parts.fragment or parts.username or parts.password:raise ValueError('Use an official HTTPS Battlelog platoon URL')
   match=PATH.fullmatch(parts.path)
   if not match:raise ValueError('Unsupported platoon URL')
   pid=int(match.group(1))
   with engine.begin() as c:
    c.execute(text("SET LOCAL statement_timeout='5000ms'"))
    known=c.execute(text('SELECT 1 FROM platoons WHERE platoon_id=:pid'),{'pid':pid}).first()
    if known:status='already_collected'
    else:
     inserted=c.execute(text("INSERT INTO platoon_requests(platoon_id) VALUES (:pid) ON CONFLICT DO NOTHING RETURNING platoon_id"),{'pid':pid}).first()
     status='queued' if inserted else 'already_queued'
   self.reply(200,{'state':status,'platoon_id':str(pid)})
  except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:self.reply(400,{'error':str(e)})
  except Exception:self.reply(503,{'error':'admission_unavailable'})
 def reply(self,status,obj):
  body=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',8792),Handler).serve_forever()
