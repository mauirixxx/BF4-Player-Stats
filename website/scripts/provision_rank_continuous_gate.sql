CREATE TABLE IF NOT EXISTS public.bf4ps_rank_wal_gate(id integer PRIMARY KEY CHECK(id=1), target_lsn pg_lsn NOT NULL, primary_started_at timestamptz NOT NULL, armed_at timestamptz NOT NULL DEFAULT clock_timestamp());
REVOKE ALL ON public.bf4ps_rank_wal_gate FROM PUBLIC;
CREATE OR REPLACE FUNCTION public.bf4ps_rank_gate_arm() RETURNS void LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
INSERT INTO public.bf4ps_rank_wal_gate VALUES(1,pg_current_wal_insert_lsn(),pg_postmaster_start_time(),clock_timestamp()) ON CONFLICT(id) DO UPDATE SET target_lsn=excluded.target_lsn,primary_started_at=excluded.primary_started_at,armed_at=excluded.armed_at;
$$;
CREATE OR REPLACE FUNCTION public.bf4ps_rank_gate_ready() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
SELECT NOT pg_is_in_recovery()
AND EXISTS(SELECT 1 FROM public.bf4ps_rank_wal_gate g WHERE g.primary_started_at=pg_postmaster_start_time() AND g.armed_at >= COALESCE((SELECT max(last_success_at) FROM public.equipment_rank_jobs),'-infinity'::timestamptz))
AND (SELECT count(*) FROM pg_catalog.pg_replication_slots r JOIN pg_catalog.pg_stat_replication s ON s.pid=r.active_pid
LEFT JOIN public.bf4ps_rank_wal_gate g ON g.id=1
WHERE r.slot_name IN ('mak_db_01','rnt_db_01','hnl_db_01','kah_db_01') AND r.slot_type='physical' AND s.state='streaming' AND s.replay_lsn IS NOT NULL AND (g.target_lsn IS NULL OR s.replay_lsn>=g.target_lsn))=4
AND (SELECT count(*) FROM pg_catalog.pg_replication_slots WHERE slot_type='physical' AND slot_name IN ('mak_db_01','rnt_db_01','hnl_db_01','kah_db_01'))=4
AND COALESCE((SELECT max(pg_wal_lsn_diff(pg_current_wal_lsn(),restart_lsn)) FROM pg_catalog.pg_replication_slots WHERE slot_type='physical'),1e30)<34359738368;
$$;
REVOKE ALL ON FUNCTION public.bf4ps_rank_gate_arm() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.bf4ps_rank_gate_ready() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.bf4ps_rank_gate_arm() TO bf4_playerstats_test_migrator;
GRANT EXECUTE ON FUNCTION public.bf4ps_rank_gate_ready() TO bf4_playerstats_test_migrator;
