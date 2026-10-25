-- Production ranking admission gate: single local physical replica.
-- Applied 2026-10-25 to mak-db-02; keep the original function backed up before changes.
-- The remote HNL, KAH and RNT replicas remain intentionally offline due to WAL/WAN limits.
CREATE OR REPLACE FUNCTION public.bf4ps_rank_gate_ready()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog'
AS $function$
SELECT NOT pg_is_in_recovery()
AND EXISTS (SELECT 1 FROM public.bf4ps_rank_wal_gate g
  WHERE g.primary_started_at=pg_postmaster_start_time()
    AND g.armed_at>=COALESCE((SELECT max(last_success_at) FROM public.equipment_rank_jobs),'-infinity'::timestamptz))
AND (SELECT count(*) FROM pg_catalog.pg_replication_slots r
  JOIN pg_catalog.pg_stat_replication s ON s.pid=r.active_pid
  LEFT JOIN public.bf4ps_rank_wal_gate g ON g.id=1
  WHERE r.slot_name='mak_db_01' AND r.slot_type='physical'
    AND s.state='streaming' AND s.replay_lsn IS NOT NULL
    AND (g.target_lsn IS NULL OR s.replay_lsn>=g.target_lsn))=1
AND (SELECT count(*) FROM pg_catalog.pg_replication_slots
  WHERE slot_type='physical' AND slot_name='mak_db_01')=1
AND COALESCE((SELECT max(pg_wal_lsn_diff(pg_current_wal_lsn(),restart_lsn))
  FROM pg_catalog.pg_replication_slots WHERE slot_type='physical'),1e30)<34359738368;
$function$;
