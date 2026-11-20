-- BF4PS standalone-primary ranking gate (bf4ps-db, 2026-11-20).
-- Deliberately fail closed if any physical replication slot or standby appears.
-- Require a fresh gate arm for this postmaster and locally flushed WAL.
-- Revisit this function before enabling streaming replication.
CREATE OR REPLACE FUNCTION public.bf4ps_rank_gate_ready()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog'
AS $function$
SELECT NOT pg_catalog.pg_is_in_recovery()
AND EXISTS (
 SELECT 1 FROM public.bf4ps_rank_wal_gate g
 WHERE g.id=1
   AND g.primary_started_at=pg_catalog.pg_postmaster_start_time()
   AND g.armed_at >= COALESCE(
     (SELECT max(last_success_at) FROM public.equipment_rank_jobs),
     '-infinity'::timestamptz)
   AND pg_catalog.pg_current_wal_flush_lsn() >= g.target_lsn
)
AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_replication_slots WHERE slot_type='physical')
AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_stat_replication);
$function$;
-- CREATE OR REPLACE preserves existing ownership and EXECUTE grants.
