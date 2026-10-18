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
  if self.path!='/submit' or self.headers.get('Content-Type')!='application/json':self.send_error(404);return
  try:
   size=int(self.headers.get('Content-Length','0'))
   if size<1 or size>1024:raise ValueError('Invalid size')
   data=json.loads(self.rfile.read(size));url=data['url'];parts=urlsplit(url)
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
