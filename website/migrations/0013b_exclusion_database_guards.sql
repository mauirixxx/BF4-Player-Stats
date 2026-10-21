-- Install after 0013_player_exclusions.sql, in a reviewed maintenance window.
-- Guard both direct database admissions and existing queued work.
-- SECURITY DEFINER functions use explicit schema-qualified references.
BEGIN;
CREATE OR REPLACE FUNCTION public.reject_excluded_soldier_job()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.soldiers s
    JOIN public.player_exclusions e ON e.platform=s.platform
      AND e.persona_id=s.persona_id AND e.active
    WHERE s.soldier_id=NEW.soldier_id
  ) THEN
    RAISE EXCEPTION 'excluded player cannot be scheduled' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_reject_excluded_soldier_job ON public.collection_jobs;
CREATE TRIGGER trg_reject_excluded_soldier_job
BEFORE INSERT OR UPDATE OF soldier_id, status ON public.collection_jobs
FOR EACH ROW WHEN (NEW.status IN ('pending','claimed','running'))
EXECUTE FUNCTION public.reject_excluded_soldier_job();

CREATE OR REPLACE FUNCTION public.reject_excluded_soldier_identity()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.player_exclusions e
             WHERE e.platform=NEW.platform AND e.persona_id=NEW.persona_id AND e.active) THEN
    RAISE EXCEPTION 'excluded player cannot be admitted' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_reject_excluded_soldier_identity ON public.soldiers;
CREATE TRIGGER trg_reject_excluded_soldier_identity
BEFORE INSERT OR UPDATE OF persona_id,platform ON public.soldiers
FOR EACH ROW EXECUTE FUNCTION public.reject_excluded_soldier_identity();

CREATE OR REPLACE FUNCTION public.reject_excluded_verification()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.player_exclusions e
             WHERE e.platform=NEW.platform AND e.persona_id=NEW.persona_id AND e.active) THEN
    RAISE EXCEPTION 'excluded player cannot be verified' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_reject_excluded_verification ON public.manual_soldier_verifications;
CREATE TRIGGER trg_reject_excluded_verification
BEFORE INSERT OR UPDATE OF persona_id,platform,status ON public.manual_soldier_verifications
FOR EACH ROW EXECUTE FUNCTION public.reject_excluded_verification();
COMMIT;
