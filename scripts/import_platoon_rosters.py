#!/usr/bin/env python3
"""Import validated Battlelog roster JSON using psql, without writing soldier tables.

Credentials come from a local PostgreSQL password file (PGPASSFILE), never CLI args.
Each roster is validated before any SQL is run; all imports commit atomically.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def literal(value):
    if value is None:
        return 'NULL'
    return "'" + str(value).replace("'", "''") + "'"


def validate(path):
    doc = json.loads(path.read_text(encoding='utf-8'))
    p, accounts, v = doc['platoon'], doc['accounts'], doc['validation']
    pid = int(p['platoon_id'])
    if pid <= 0 or not v.get('complete') or not p['name'] or p['tag'] is None:
        raise ValueError(f'{path}: incomplete or invalid platoon')
    if len(accounts) != int(p['official_member_count']) or len(accounts) != int(v['account_count']):
        raise ValueError(f'{path}: inconsistent account counts')
    ids = [int(a['battlelog_account_id']) for a in accounts]
    if any(i <= 0 for i in ids) or len(ids) != len(set(ids)):
        raise ValueError(f'{path}: invalid or duplicate account ID')
    total = 0
    for a in accounts:
        if a['role'] not in ('founder', 'leader', 'member'):
            raise ValueError('Invalid role')
        seen = set()
        for x in a['bf4_personas']:
            key = (int(x['battlelog_platform_code']), int(x['persona_id']))
            if key in seen or key[0] not in (1, 2, 4, 32, 64) or key[1] <= 0:
                raise ValueError('Invalid or duplicate persona association')
            if x['platform_family'] not in ('pc', 'xbox', 'playstation') or not x['persona_name']:
                raise ValueError('Invalid persona evidence')
            seen.add(key)
            total += 1
    if total != int(v['bf4_platform_records']):
        raise ValueError(f'{path}: inconsistent persona counts')
    return doc


def sql_for(doc):
    p, accounts = doc['platoon'], doc['accounts']
    pid = int(p['platoon_id'])
    q = [f"INSERT INTO platoons(platoon_id,name,tag,official_member_count,battlelog_created_at,last_checked_at,last_success_at,last_error) VALUES ({pid},{literal(p['name'])},{literal(p['tag'])},{int(p['official_member_count'])},{literal(p.get('created_at'))},now(),now(),NULL) ON CONFLICT(platoon_id) DO UPDATE SET name=EXCLUDED.name,tag=EXCLUDED.tag,official_member_count=EXCLUDED.official_member_count,battlelog_created_at=EXCLUDED.battlelog_created_at,last_checked_at=now(),last_success_at=now(),last_error=NULL;"]
    # Full validated snapshot only: mark absent associations former, preserving history.
    q.append(f'UPDATE platoon_roster_personas SET is_current=false WHERE platoon_id={pid};')
    q.append(f'UPDATE platoon_roster_accounts SET is_current=false WHERE platoon_id={pid};')
    for a in accounts:
        aid = int(a['battlelog_account_id'])
        q.append(f"INSERT INTO platoon_roster_accounts(platoon_id,battlelog_account_id,account_name,role,joined_at,is_current,last_seen_at) VALUES ({pid},{aid},{literal(a.get('account_name'))},{literal(a['role'])},{literal(a.get('joined_at'))},true,now()) ON CONFLICT(platoon_id,battlelog_account_id) DO UPDATE SET account_name=EXCLUDED.account_name,role=EXCLUDED.role,joined_at=EXCLUDED.joined_at,is_current=true,last_seen_at=now();")
        for x in a['bf4_personas']:
            code = int(x['battlelog_platform_code'])
            persona = int(x['persona_id'])
            q.append(f"INSERT INTO platoon_roster_personas(platoon_id,battlelog_account_id,battlelog_platform_code,persona_id,persona_name,platform_family,is_current,last_seen_at) VALUES ({pid},{aid},{code},{persona},{literal(x['persona_name'])},{literal(x['platform_family'])},true,now()) ON CONFLICT(platoon_id,battlelog_account_id,battlelog_platform_code,persona_id) DO UPDATE SET persona_name=EXCLUDED.persona_name,platform_family=EXCLUDED.platform_family,is_current=true,last_seen_at=now();")
    q.append(f"INSERT INTO platoon_sync_runs(platoon_id,completed_at,success,account_count,bf4_platform_records) VALUES ({pid},now(),true,{len(accounts)},{sum(len(a['bf4_personas']) for a in accounts)});")
    return q


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rosters', nargs='+', type=Path)
    parser.add_argument('--host', default='db.bf4statusbot.com')
    parser.add_argument('--database', default='bf4_playerstats')
    parser.add_argument('--user', default='bf4ps_platoon_collector')
    parser.add_argument('--password-file', type=Path, default=Path('/root/.config/bf4ps/platoon-db-password'))
    args = parser.parse_args()
    docs = [validate(p) for p in args.rosters]
    if len({int(d['platoon']['platoon_id']) for d in docs}) != len(docs):
        raise ValueError('Duplicate platoon input')
    password = args.password_file.read_text().strip()
    if not password or ':' in password or '\n' in password or '\\' in password:
        raise ValueError('Password format unsupported for temporary pgpass')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='bf4ps-platoon-') as tmp:
        pgpass = Path(tmp) / 'pgpass'
        pgpass.write_text(f'{args.host}:5432:{args.database}:{args.user}:{password}\n')
        pgpass.chmod(0o600)
        statements = ['BEGIN;', 'SET LOCAL statement_timeout = \'120s\';']
        for doc in docs:
            statements.extend(sql_for(doc))
        statements.append('COMMIT;')
        sqlpath = Path(tmp) / 'import.sql'
        sqlpath.write_text('\n'.join(statements) + '\n')
        env = dict(os.environ, PGPASSFILE=str(pgpass), PGCONNECT_TIMEOUT='8', PGSSLMODE='require')
        command = ['psql', '-X', '-w', '-v', 'ON_ERROR_STOP=1', '-h', args.host, '-U', args.user, '-d', args.database, '-f', str(sqlpath)]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        if result.returncode:
            print('Import failed (transaction rolled back):', result.stderr[-1800:], file=sys.stderr)
            return result.returncode
        verify = subprocess.run(['psql','-X','-w','-At','-h',args.host,'-U',args.user,'-d',args.database,'-c',"SELECT p.platoon_id,p.name,(SELECT count(*) FROM platoon_roster_accounts a WHERE a.platoon_id=p.platoon_id AND a.is_current),(SELECT count(*) FROM platoon_roster_personas x WHERE x.platoon_id=p.platoon_id AND x.is_current) FROM platoons p ORDER BY p.platoon_id;"],env=env,capture_output=True,text=True)
        if verify.returncode:
            print('Import committed, verification failed:',verify.stderr,file=sys.stderr)
            return verify.returncode
        print('Committed platoon rosters (id|name|current accounts|current persona evidence):')
        print(verify.stdout.strip())
    return 0


if __name__ == '__main__':
    sys.exit(main())
