BEGIN;
GRANT INSERT ON public.soldiers, public.soldier_names, public.soldier_sources, public.collection_state TO bf4ps_manual_function_owner;
GRANT SELECT ON public.soldier_names, public.soldier_sources TO bf4ps_manual_function_owner;
GRANT UPDATE (last_seen_at) ON public.soldier_names, public.soldier_sources TO bf4ps_manual_function_owner;
GRANT USAGE ON SEQUENCE public.soldiers_soldier_id_seq, public.soldier_names_soldier_name_id_seq TO bf4ps_manual_function_owner;
CREATE OR REPLACE FUNCTION manual_api.submit_soldier_url(p_persona_id bigint,p_platform text,p_name text,p_kind text)
RETURNS TABLE(request_id bigint,state text,retry_after_seconds integer,jobs_created integer,jobs_promoted integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $body$
DECLARE v_soldier bigint; v_new boolean := false;
BEGIN
 IF p_persona_id IS NULL OR p_persona_id < 1 OR p_platform NOT IN ('pc','ps4','xboxone')
 OR p_kind NOT IN ('add','refresh') OR p_name IS NULL OR length(p_name) NOT BETWEEN 1 AND 80
 OR p_name !~ '^[A-Za-z0-9_.~-]+$' THEN
  RAISE EXCEPTION 'invalid soldier submission' USING ERRCODE='22023';
 END IF;
 IF p_kind='add' THEN
  INSERT INTO public.soldiers(persona_id,platform,current_name,first_seen_at,last_seen_at)
  VALUES(p_persona_id,p_platform,p_name,clock_timestamp(),clock_timestamp())
  ON CONFLICT(persona_id,platform) DO NOTHING
  RETURNING soldier_id INTO v_soldier;
  v_new := v_soldier IS NOT NULL;
  IF NOT v_new THEN
   SELECT soldier_id INTO v_soldier FROM public.soldiers
   WHERE persona_id=p_persona_id AND platform=p_platform FOR UPDATE;
  END IF;
  INSERT INTO public.soldier_names(soldier_id,name,first_seen_at,last_seen_at)
  VALUES(v_soldier,p_name,clock_timestamp(),clock_timestamp())
  ON CONFLICT(soldier_id,name) DO UPDATE SET last_seen_at=EXCLUDED.last_seen_at;
  INSERT INTO public.soldier_sources(soldier_id,source_type,first_seen_at,last_seen_at)
  VALUES(v_soldier,'manual',clock_timestamp(),clock_timestamp())
  ON CONFLICT(soldier_id,source_type) DO UPDATE SET last_seen_at=EXCLUDED.last_seen_at;
  INSERT INTO public.collection_state(soldier_id) VALUES(v_soldier) ON CONFLICT DO NOTHING;
 END IF;
 RETURN QUERY SELECT x.request_id,x.state,x.retry_after_seconds,x.jobs_created,x.jobs_promoted
 FROM manual_api.request_existing_soldier(p_persona_id,p_platform,p_kind) AS x;
END $body$;
ALTER FUNCTION manual_api.submit_soldier_url(bigint,text,text,text) OWNER TO bf4ps_manual_function_owner;
REVOKE ALL ON FUNCTION manual_api.submit_soldier_url(bigint,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION manual_api.submit_soldier_url(bigint,text,text,text) TO bf4ps_manual_api;
COMMIT;