"""Bounded read-only per-soldier detail; columns mirror snapshot exporter."""
from sqlalchemy import text

SOLDIER_SQL=text("""select s.soldier_id, s.current_name, s.persona_id, s.platform,
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
                where s.soldier_id=:soldier_id AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
                """)
WEAPON_SQL=text("""
SELECT w.soldier_id,w.weapon_id AS equipment_id,c.name,c.category,w.kills,
       w.headshots,w.shots_fired,w.shots_hit,w.time_equipped_seconds
FROM soldier_weapon_stats w JOIN weapon_catalog c ON c.weapon_id=w.weapon_id
WHERE w.soldier_id=:soldier_id ORDER BY w.kills DESC,w.weapon_id LIMIT 15
""")
VEHICLE_SQL=text("""
SELECT v.soldier_id,v.vehicle_id AS equipment_id,c.name,c.category,v.kills,v.time_in_seconds
FROM soldier_vehicle_stats v JOIN vehicle_catalog c ON c.vehicle_id=v.vehicle_id
WHERE v.soldier_id=:soldier_id ORDER BY v.kills DESC,v.vehicle_id LIMIT 15
""")

def get_soldier_detail(conn,soldier_id):
    if not isinstance(soldier_id,int) or not 1<=soldier_id<=9223372036854775807:
        raise ValueError('Invalid soldier ID')
    args={'soldier_id':soldier_id}
    soldier=conn.execute(SOLDIER_SQL,args).mappings().first()
    if soldier is None:return None
    return {'soldier':dict(soldier),
            'weapons':[dict(r) for r in conn.execute(WEAPON_SQL,args).mappings()],
            'vehicles':[dict(r) for r in conn.execute(VEHICLE_SQL,args).mappings()]}
