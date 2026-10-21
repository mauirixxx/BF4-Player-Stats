#!/usr/bin/env python3
"""Temporary read-only snapshot exporter; credentials never enter the web root."""
import json, os, time
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, text

OUT = Path('/var/www/bf4playerstats.com/temp-stats-data.json')
SUMMARY_OUT = OUT.with_name('homepage-summary.json')
engine = create_engine(os.environ['BF4PS_DATABASE_URL'], pool_pre_ping=True)

def rows(conn, sql):
    return [dict(x) for x in conn.execute(text(sql)).mappings()]

def homepage_summary(payload):
    soldiers = payload['soldiers']
    detailed = sum(s.get('detailed_state') == 'success' for s in soldiers)
    full = sum(all(s.get(k) == 'success' for k in
                   ('detailed_state', 'weapons_state', 'vehicles_state', 'profile_state'))
               for s in soldiers)
    return {'updated': payload['updated'], 'summary': payload['summary'],
            'detailed_soldiers': detailed, 'full_soldiers': full}

def export():
    with engine.connect() as c:
        db = c.execute(text('select current_database()')).scalar_one()
        if db != 'bf4_playerstats':
            raise RuntimeError('Refusing non-scratch database')
        payload = {
            'updated': datetime.now(timezone.utc).isoformat(),
            'database': db,
            'summary': dict(c.execute(text("""
                select
                  (select count(*) from soldiers s WHERE NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)) soldiers,
                  (select count(*) from soldier_weapon_stats w JOIN soldiers s ON s.soldier_id=w.soldier_id WHERE NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)) weapons,
                  (select count(*) from soldier_vehicle_stats v JOIN soldiers s ON s.soldier_id=v.soldier_id WHERE NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)) vehicles,
                  (select count(*) from profile_soldiers ps JOIN soldiers s ON s.soldier_id=ps.soldier_id WHERE NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)) profiles,
                  (select count(*) from collection_jobs where status='pending') pending,
                  (select count(*) from collection_jobs where status in ('running','claimed')) running,
                  (select count(*) from collection_events where event_type='collection_success') successes,
                  (select count(*) from collection_events where event_type='collection_failure') failures,
                  pg_database_size(current_database()) db_bytes
            """)).mappings().one()),
            'failure_health': dict(c.execute(text("""
                WITH failed_jobs AS (
                    SELECT DISTINCT job_id FROM collection_events
                    WHERE event_type='collection_failure' AND job_id IS NOT NULL
                ), classified AS (
                    SELECT f.job_id,
                           EXISTS(SELECT 1 FROM collection_events e
                                  WHERE e.job_id=f.job_id AND e.event_type='collection_success') recovered,
                           j.status, j.eligible_at
                    FROM failed_jobs f LEFT JOIN collection_jobs j ON j.job_id=f.job_id
                )
                SELECT count(*) affected_jobs,
                       count(*) FILTER (WHERE recovered) recovered_jobs,
                       count(*) FILTER (WHERE NOT recovered) outstanding_jobs,
                       count(*) FILTER (WHERE NOT recovered AND status='pending') retry_pending,
                       count(*) FILTER (WHERE NOT recovered AND status IN ('claimed','running')) retry_in_progress,
                       count(*) FILTER (WHERE NOT recovered AND status IS NULL) missing_jobs,
                       min(eligible_at) FILTER (WHERE NOT recovered AND status='pending') next_retry_at
                FROM classified
            """)).mappings().one()),
            'failure_reasons': rows(c, """
                SELECT resource,error_class,coalesce(http_status::text,'—') http_status,
                       count(*) failure_events
                FROM collection_events WHERE event_type='collection_failure'
                GROUP BY resource,error_class,http_status ORDER BY failure_events DESC
            """),
            'soldiers': rows(c, """
                select s.soldier_id, s.current_name, s.persona_id, s.platform,
                       cs.detailed_state,cs.weapons_state,cs.vehicles_state,cs.profile_state,
                       cs.detailed_last_success_at,cs.weapons_last_success_at,cs.vehicles_last_success_at,cs.profile_last_success_at,
                       d.rank,d.kills,d.deaths,d.wins,d.losses,d.total_score,d.time_played_seconds,
                       d.assault_score, d.engineer_score, d.support_score, d.recon_score, d.commander_score, d.squad_score, d.vehicle_score, d.award_score, d.unlock_score, d.combat_score, d.conquest_score, d.rush_score, d.team_deathmatch_score, d.domination_score, d.obliteration_score, d.defuse_score, d.capture_the_flag_score, d.air_superiority_score, d.carrier_assault_score, d.chain_link_score, d.kill_assists, d.shots_fired, d.shots_hit, d.repairs, d.revives, d.heals, d.resupplies, d.avenger_kills, d.savior_kills, d.suppression_assists, d.quit_percentage, d.flags_captured, d.flags_defended, d.dogtags_taken, d.vehicles_destroyed, d.vehicle_damage, d.headshots, d.longest_headshot, d.highest_kill_streak, d.nemesis_kills, d.highest_nemesis_streak,
                       bp.battlelog_username,bp.country_code,bp.country_name,
                       (select count(*) from soldier_weapon_stats w where w.soldier_id=s.soldier_id) weapon_count,
                       (select count(*) from soldier_vehicle_stats v where v.soldier_id=s.soldier_id) vehicle_count
                from soldiers s
                left join collection_state cs on cs.soldier_id=s.soldier_id
                left join detailed_stats_current d on d.soldier_id=s.soldier_id
                left join lateral (
                    select bp.battlelog_username,bp.country_code,bp.country_name from profile_soldiers ps
                    join battlelog_profiles bp on bp.profile_id=ps.profile_id
                    where ps.soldier_id=s.soldier_id order by ps.last_seen_at desc limit 1
                ) bp on true
                where NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) AND (cs.detailed_state='success' or cs.weapons_state='success'
                   or cs.vehicles_state='success' or cs.profile_state='success')
                order by s.soldier_id desc
            """),
            'weapons': rows(c, """
                select ranked.soldier_id,ranked.weapon_id AS equipment_id,cat.name,cat.category,ranked.kills,ranked.headshots,ranked.shots_fired,ranked.shots_hit,ranked.time_equipped_seconds
                from (select w.*,row_number() over (partition by soldier_id order by kills desc,weapon_id) as position from soldier_weapon_stats w) ranked
                join weapon_catalog cat on cat.weapon_id=ranked.weapon_id
                where ranked.position <= 15 AND EXISTS (SELECT 1 FROM soldiers s WHERE s.soldier_id=ranked.soldier_id AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active))
                order by ranked.soldier_id,ranked.position
            """),
            'vehicles': rows(c, """
                select ranked.soldier_id,ranked.vehicle_id AS equipment_id,cat.name,cat.category,ranked.kills,ranked.time_in_seconds
                from (select v.*,row_number() over (partition by soldier_id order by kills desc,vehicle_id) as position from soldier_vehicle_stats v) ranked
                join vehicle_catalog cat on cat.vehicle_id=ranked.vehicle_id
                where ranked.position <= 15 AND EXISTS (SELECT 1 FROM soldiers s WHERE s.soldier_id=ranked.soldier_id AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active))
                order by ranked.soldier_id,ranked.position
            """),
            'recent': rows(c, """
                select occurred_at,hostname_snapshot,resource,event_type,platform
                from collection_events order by event_id desc limit 30
            """)
        }
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload,default=str,separators=(',',':')))
    os.chmod(tmp,0o644)
    os.replace(tmp,OUT)
    # Derived from the same completed snapshot: no extra database queries.
    # Write atomically so readers never see a partially generated response.
    compact = homepage_summary(payload)
    small_tmp = SUMMARY_OUT.with_suffix('.json.tmp')
    small_tmp.write_text(json.dumps(compact, separators=(',',':')))
    os.chmod(small_tmp, 0o644)
    os.replace(small_tmp, SUMMARY_OUT)

if __name__=='__main__':
    while True:
        try: export()
        except Exception as exc: print('export error:',type(exc).__name__,str(exc)[:200],flush=True)
        time.sleep(5)
