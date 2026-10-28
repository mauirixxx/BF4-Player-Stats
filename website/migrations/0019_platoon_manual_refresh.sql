-- Applied on production mak-db-02 on 2026-10-28.
-- Dedicated durable cooldown and least-privilege scheduler entry point.
BEGIN;
CREATE TABLE IF NOT EXISTS public.platoon_manual_refresh (
 platoon_id bigint PRIMARY KEY REFERENCES public.platoons(platoon_id) ON DELETE CASCADE,
 last_requested_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON public.platoon_manual_refresh FROM PUBLIC;
CREATE OR REPLACE FUNCTION public.request_platoon_refresh(p_id bigint,p_bypass boolean DEFAULT false)
RETURNS TABLE(state text,retry_after_seconds integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE last_at timestamptz; due timestamptz;
BEGIN
 IF p_id IS NULL OR p_id<=0 THEN RAISE EXCEPTION 'invalid platoon'; END IF;
 PERFORM 1 FROM public.platoons WHERE platoon_id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN QUERY SELECT 'not_found'::text,0; RETURN; END IF;
 SELECT last_requested_at INTO last_at FROM public.platoon_manual_refresh WHERE platoon_id=p_id FOR UPDATE;
 IF NOT p_bypass AND last_at IS NOT NULL AND last_at > now()-interval '60 minutes' THEN
  RETURN QUERY SELECT 'cooldown'::text,GREATEST(1,CEIL(EXTRACT(EPOCH FROM (last_at+interval '60 minutes'-now())))::integer); RETURN;
 END IF;
 SELECT next_refresh_at INTO due FROM public.platoons WHERE platoon_id=p_id;
 IF due IS NOT NULL AND due BETWEEN now() AND now()+interval '15 minutes' THEN
  RETURN QUERY SELECT 'already_queued'::text,0; RETURN;
 END IF;
 INSERT INTO public.platoon_manual_refresh(platoon_id,last_requested_at) VALUES(p_id,now())
 ON CONFLICT(platoon_id) DO UPDATE SET last_requested_at=excluded.last_requested_at;
 UPDATE public.platoons SET next_refresh_at=now()-interval '1 second' WHERE platoon_id=p_id;
 RETURN QUERY SELECT 'queued'::text,0;
END $$;
REVOKE ALL ON FUNCTION public.request_platoon_refresh(bigint,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.request_platoon_refresh(bigint,boolean) TO bf4ps_stage9c_d2;
COMMIT;
