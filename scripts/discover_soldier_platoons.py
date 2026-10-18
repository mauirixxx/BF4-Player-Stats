#!/usr/bin/env python3
"""Low-rate soldier-page discovery: enqueue linked official platoons, never infer active tag ownership."""
import fcntl
import html.parser
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from platoon_queue_worker import query, BASE

class SoldierHeader(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(); self.club_ids=[]; self.tag=None; self.in_name=False; self.name_depth=0; self.in_tag=False; self.in_club=False; self.club_depth=0
    def handle_starttag(self, tag, attrs):
        a=dict(attrs); classes=set(a.get('class','').split())
        if tag=='h1' and 'soldier-info-name' in classes: self.in_name=True; self.name_depth=1
        elif self.in_name and tag in ('span','h1'):
            self.name_depth+=1
            if tag=='span' and self.tag is None:self.in_tag=True
        if tag=='span' and 'club-link' in classes:
            self.in_club=True;self.club_depth=1
        elif self.in_club and tag=='span':self.club_depth+=1
        if tag=='a' and self.in_club:
            href=a.get('href','');m=re.fullmatch(r'/bf4/platoons/view/([1-9][0-9]{0,18})/',href)
            if m:self.club_ids.append(int(m.group(1)))
    def handle_endtag(self,tag):
        if tag=='span' and self.in_club:
            self.club_depth-=1
            if self.club_depth==0:self.in_club=False
        if self.in_name and tag in ('span','h1'):
            if tag=='span':self.in_tag=False
            self.name_depth-=1
            if self.name_depth==0:self.in_name=False
    def handle_data(self,data):
        if self.in_tag and self.tag is None and data.strip().startswith('[') and data.strip().endswith(']'):self.tag=data.strip()

def esc(value):return "'"+str(value).replace("'","''")+"'"

def seed():
    # Only current supported-platform identities observed in confirmed platoon rosters.
    return query("""INSERT INTO platoon_soldier_discovery(soldier_id)
      SELECT DISTINCT s.soldier_id FROM platoon_roster_personas p
      JOIN platoon_roster_accounts a ON a.platoon_id=p.platoon_id AND a.battlelog_account_id=p.battlelog_account_id AND a.is_current
      JOIN soldiers s ON s.persona_id=p.persona_id AND s.platform=CASE p.battlelog_platform_code WHEN 1 THEN 'pc' WHEN 32 THEN 'ps4' WHEN 64 THEN 'xboxone' END
      WHERE p.is_current AND p.battlelog_platform_code IN (1,32,64)
      ON CONFLICT DO NOTHING""")

def main():
    BASE.mkdir(parents=True,exist_ok=True)
    with (BASE/'.discovery.lock').open('w') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 0
        print('Seed:',seed(),flush=True)
        row=query("""SELECT d.soldier_id,s.persona_id,s.platform,s.current_name
          FROM platoon_soldier_discovery d JOIN soldiers s USING(soldier_id)
          WHERE d.status IN ('pending','failed') AND d.next_attempt_at<=now() AND d.attempts<5
          ORDER BY d.next_attempt_at,d.soldier_id LIMIT 1""")
        if not row:print('No discovery due');return 0
        soldier,persona,platform,name=row.split('|',3)
        query(f"UPDATE platoon_soldier_discovery SET status='running',attempts=attempts+1 WHERE soldier_id={int(soldier)}")
        try:
            if platform not in ('pc','ps4','xboxone') or not re.fullmatch(r'[0-9]+',persona):raise ValueError('unsupported identity')
            from urllib.parse import quote
            url=f'https://battlelog.battlefield.com/bf4/soldier/{quote(name,safe="")}/stats/{persona}/{platform}/'
            request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; BF4PSPlatoonWatcher/1.0)'})
            with urllib.request.urlopen(request,timeout=25) as response:
                if response.status!=200 or urlsplit(response.url).hostname!='battlelog.battlefield.com':raise ValueError('unexpected response')
                content=response.read(1_000_001)
            if len(content)>1_000_000:raise ValueError('oversized soldier page')
            print('HTTP soldier bytes',len(content),'status',response.status,flush=True)
            source=content.decode('utf-8','replace')
            if 'soldier-info-name' not in source:raise ValueError('missing soldier header')
            parser=SoldierHeader();parser.feed(source)
            ids=set(parser.club_ids)
            if len(ids)>1:raise ValueError('ambiguous linked platoons')
            linked=next(iter(ids),None)
            # Only queue a verified numeric ID from the soldier page, never a tag guess.
            if linked:
                query(f"""INSERT INTO platoon_requests(platoon_id)
                  SELECT {linked} WHERE NOT EXISTS(SELECT 1 FROM platoons WHERE platoon_id={linked})
                  ON CONFLICT DO NOTHING""")
            tag=esc(parser.tag) if parser.tag else 'NULL'
            query(f"UPDATE platoon_soldier_discovery SET status='complete',last_checked_at=now(),linked_platoon_id={linked if linked else 'NULL'},displayed_tag={tag},last_error=NULL WHERE soldier_id={int(soldier)}")
            print('Discovered soldier',soldier,'linked platoon',linked,'display tag',parser.tag,flush=True)
            return 0
        except Exception as exc:
            error=esc(str(exc)[:250]);query(f"UPDATE platoon_soldier_discovery SET status='failed',last_error={error},next_attempt_at=now()+interval '1 hour'*LEAST(24,power(2,LEAST(attempts,4))::integer) WHERE soldier_id={int(soldier)}")
            print('Discovery failed',soldier,str(exc),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
