#!/usr/bin/env python3
"""Idempotent platoon soldier bootstrap; existing soldiers are never modified."""
from platoon_queue_worker import query

SQL = r'''
BEGIN;
SET LOCAL statement_timeout = '30s';
CREATE TEMP TABLE _platoon_new_soldiers (soldier_id bigint PRIMARY KEY) ON COMMIT DROP;
WITH candidates AS (
 SELECT DISTINCT ON (p.persona_id, p.battlelog_platform_code)
        p.persona_id,
        CASE p.battlelog_platform_code WHEN 1 THEN 'pc' WHEN 32 THEN 'ps4' WHEN 64 THEN 'xboxone' END AS platform,
        btrim(p.persona_name) AS name
 FROM platoon_roster_personas p
 JOIN platoon_roster_accounts a ON a.platoon_id=p.platoon_id AND a.battlelog_account_id=p.battlelog_account_id AND a.is_current
 WHERE p.is_current AND p.battlelog_platform_code IN (1,32,64)
       AND btrim(p.persona_name) <> ''
 ORDER BY p.persona_id,p.battlelog_platform_code,p.last_seen_at DESC,p.platoon_id
), inserted AS (
 INSERT INTO soldiers(soldier_id,persona_id,platform,current_name,first_seen_at,last_seen_at)
 SELECT nextval('soldiers_soldier_id_seq'),c.persona_id,c.platform,c.name,now(),now()
 FROM candidates c
 ON CONFLICT (persona_id,platform) DO NOTHING
 RETURNING soldier_id
)
INSERT INTO _platoon_new_soldiers SELECT soldier_id FROM inserted;
INSERT INTO collection_state(soldier_id)
SELECT soldier_id FROM _platoon_new_soldiers ON CONFLICT (soldier_id) DO NOTHING;
INSERT INTO collection_jobs(job_id,soldier_id,resource,lane,priority_class,reason,status,priority_value,eligible_at)
SELECT nextval('collection_jobs_job_id_seq'),s.soldier_id,r.resource,'background','bootstrap','platoon-roster-bootstrap','pending',0,now()
FROM _platoon_new_soldiers s CROSS JOIN (VALUES ('detailed'),('profile'),('weapons'),('vehicles')) r(resource)
ON CONFLICT (soldier_id,resource) DO NOTHING;
SELECT count(*) AS new_soldiers FROM _platoon_new_soldiers;
COMMIT;
'''

if __name__=='__main__':
    print(query(SQL))
