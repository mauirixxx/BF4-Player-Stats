-- Run on the BF4PS writable primary as postgres. Re-runnable.
CREATE TABLE IF NOT EXISTS public.platoon_collector_errors (
 error_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 occurred_at timestamptz NOT NULL DEFAULT now(),
 hostname text NOT NULL,work_kind text NOT NULL,error_class text NOT NULL,error_message text NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_platoon_collector_errors_recent ON public.platoon_collector_errors(occurred_at DESC);
GRANT INSERT ON public.platoon_collector_errors TO bf4ps_platoon_collector;
GRANT USAGE ON SEQUENCE public.platoon_collector_errors_error_id_seq TO bf4ps_platoon_collector;
CREATE OR REPLACE FUNCTION public.bf4ps_admin_recent_errors()
RETURNS TABLE(happened_at timestamptz,source text,node text,category text,error_class text,message text,http_status integer,reference text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT e.occurred_at,'player'::text,e.hostname_snapshot,e.resource,coalesce(e.error_class,e.result),left(coalesce(e.error_message,''),1200),e.http_status,e.job_id::text
 FROM (SELECT occurred_at,hostname_snapshot,resource,error_class,result,error_message,http_status,job_id FROM public.collection_events WHERE error_class IS NOT NULL OR event_type='collection_failure' ORDER BY occurred_at DESC LIMIT 50) e
 UNION ALL
 SELECT p.occurred_at,'platoon'::text,p.hostname,p.work_kind,p.error_class,left(p.error_message,1200),NULL::integer,p.error_id::text
 FROM (SELECT * FROM public.platoon_collector_errors ORDER BY occurred_at DESC LIMIT 50) p
 ORDER BY 1 DESC LIMIT 50;
$$;
REVOKE ALL ON FUNCTION public.bf4ps_admin_recent_errors() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.bf4ps_admin_recent_errors() TO bf4ps_admin_moderation;
