-- Run as a PostgreSQL superuser on the writable bf4_playerstats primary.
-- Exposes aggregate streaming/lag counts, not replica addresses or credentials.
-- The admin application role only receives EXECUTE on this narrow function.
BEGIN;
CREATE OR REPLACE FUNCTION public.bf4ps_admin_replication_status()
RETURNS TABLE(streaming_replicas integer,total_replicas integer,max_replay_lag_bytes bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT count(*) FILTER (WHERE state='streaming')::integer,
        count(*)::integer,
        max(pg_wal_lsn_diff(pg_current_wal_lsn(),replay_lsn))::bigint
 FROM pg_catalog.pg_stat_replication;
$$;
REVOKE ALL ON FUNCTION public.bf4ps_admin_replication_status() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.bf4ps_admin_replication_status() TO bf4ps_admin_moderation;
COMMIT;

-- Ranking-worker admission: same aggregate telemetry, execute only for the
-- production rank-worker DB role. No access to pg_stat_replication itself.
DROP FUNCTION IF EXISTS public.bf4ps_rank_replication_admission_status();
CREATE FUNCTION public.bf4ps_rank_replication_admission_status()
RETURNS TABLE(streaming_replicas integer,total_replicas integer,max_replay_lag_bytes bigint,max_retained_wal_bytes bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT count(*) FILTER (WHERE s.state='streaming' AND r.slot_name IN ('mak_db_01','rnt_db_01'))::integer,
        count(*) FILTER (WHERE r.slot_name IN ('mak_db_01','rnt_db_01'))::integer,
        max(pg_wal_lsn_diff(pg_current_wal_lsn(),s.replay_lsn)) FILTER (WHERE r.slot_name IN ('mak_db_01','rnt_db_01'))::bigint,
        (SELECT max(pg_wal_lsn_diff(pg_current_wal_lsn(),restart_lsn))::bigint FROM pg_catalog.pg_replication_slots WHERE slot_type='physical')
 FROM pg_catalog.pg_replication_slots r LEFT JOIN pg_catalog.pg_stat_replication s ON s.pid=r.active_pid
 WHERE r.slot_type='physical';
$$;
REVOKE ALL ON FUNCTION public.bf4ps_rank_replication_admission_status() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.bf4ps_rank_replication_admission_status() TO bf4_playerstats_test_migrator;
