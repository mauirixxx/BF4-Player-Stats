"""Restricted manual API function; no login role or production activation.

Revision ID: 0010_manual_api_function
Revises: 0009_manual_requests
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_manual_api_function'
down_revision = '0009_manual_requests'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE SCHEMA IF NOT EXISTS manual_api')
    op.execute('REVOKE ALL ON SCHEMA manual_api FROM PUBLIC')
    op.execute('''
    CREATE FUNCTION manual_api.request_existing_soldier(
      p_persona_id bigint, p_platform text, p_kind text DEFAULT 'refresh'
    ) RETURNS TABLE(request_id bigint, state text, retry_after_seconds integer,
                    jobs_created integer, jobs_promoted integer)
    LANGUAGE plpgsql SECURITY INVOKER
    SET search_path = pg_catalog, pg_temp
    AS $function$
    DECLARE
      v_soldier bigint;
      v_now timestamptz;
      v_previous record;
      v_needed text[];
      v_request bigint;
      v_promoted integer := 0;
      v_created integer := 0;
      v_remaining double precision;
    BEGIN
      IF p_persona_id IS NULL OR p_persona_id <= 0 OR
         p_platform IS NULL OR p_platform NOT IN ('pc','ps4','xboxone') OR
         p_kind IS NULL OR p_kind NOT IN ('add','refresh') THEN
        RAISE EXCEPTION 'invalid manual request' USING ERRCODE = '22023';
      END IF;
      SELECT s.soldier_id INTO v_soldier
      FROM public.soldiers AS s
      WHERE s.persona_id = p_persona_id AND s.platform = p_platform
      FOR UPDATE;
      IF NOT FOUND THEN
        RETURN QUERY SELECT NULL::bigint, 'not_registered'::text, 0, 0, 0;
        RETURN;
      END IF;
      v_now := clock_timestamp();
      SELECT c.last_accepted_at, c.last_request_id INTO v_previous
      FROM public.manual_request_cooldowns AS c
      WHERE c.soldier_id = v_soldier FOR UPDATE;
      IF FOUND THEN
        v_remaining := EXTRACT(EPOCH FROM (v_previous.last_accepted_at + interval '1 hour' - v_now));
        IF v_remaining > 0 THEN
          RETURN QUERY SELECT v_previous.last_request_id, 'cooldown'::text,
                              CEIL(v_remaining)::integer, 0, 0;
          RETURN;
        END IF;
      END IF;
      SELECT ARRAY_REMOVE(ARRAY[
        CASE WHEN cs.detailed_last_success_at IS NULL OR cs.detailed_last_success_at <= v_now - interval '1 hour' THEN 'detailed' END,
        CASE WHEN cs.weapons_last_success_at IS NULL OR cs.weapons_last_success_at <= v_now - interval '1 hour' THEN 'weapons' END,
        CASE WHEN cs.vehicles_last_success_at IS NULL OR cs.vehicles_last_success_at <= v_now - interval '1 hour' THEN 'vehicles' END,
        CASE WHEN cs.profile_last_success_at IS NULL OR cs.profile_last_success_at <= v_now - interval '1 hour' THEN 'profile' END
      ], NULL) INTO v_needed
      FROM public.collection_state AS cs WHERE cs.soldier_id = v_soldier;
      IF NOT FOUND THEN
        v_needed := ARRAY['detailed','weapons','vehicles','profile'];
      END IF;
      IF cardinality(v_needed) = 0 THEN
        RETURN QUERY SELECT NULL::bigint, 'up_to_date'::text, 0, 0, 0;
        RETURN;
      END IF;
      INSERT INTO public.manual_collection_requests(soldier_id,request_kind,status,requested_at)
      VALUES (v_soldier,p_kind,'accepted',v_now) RETURNING manual_collection_requests.request_id INTO v_request;
      INSERT INTO public.manual_request_cooldowns(soldier_id,last_accepted_at,last_request_id)
      VALUES (v_soldier,v_now,v_request)
      ON CONFLICT (soldier_id) DO UPDATE
      SET last_accepted_at = EXCLUDED.last_accepted_at,
          last_request_id = EXCLUDED.last_request_id;
      WITH changed AS (
        UPDATE public.collection_jobs AS j
        SET priority_class = 'interactive', priority_value = GREATEST(j.priority_value,100),
            reason = 'manual_refresh', updated_at = v_now
        WHERE j.soldier_id = v_soldier AND j.resource = ANY(v_needed)
          AND j.lane = 'background' AND j.status = 'pending'
          AND j.last_error_at IS NULL AND j.eligible_at <= v_now
        RETURNING j.job_id
      ) SELECT count(*)::integer INTO v_promoted FROM changed;
      WITH added AS (
        INSERT INTO public.collection_jobs
          (soldier_id,resource,lane,priority_class,reason,status,priority_value,eligible_at)
        SELECT v_soldier, r, 'background','interactive','manual_request','pending',100,v_now
        FROM unnest(v_needed) AS r
        ON CONFLICT (soldier_id,resource) DO NOTHING
        RETURNING job_id
      ) SELECT count(*)::integer INTO v_created FROM added;
      RETURN QUERY SELECT v_request, 'accepted'::text, 0, v_created, v_promoted;
    END
    $function$
    ''')
    op.execute('REVOKE ALL ON FUNCTION manual_api.request_existing_soldier(bigint,text,text) FROM PUBLIC')


def downgrade():
    op.execute('DROP FUNCTION manual_api.request_existing_soldier(bigint,text,text)')
    op.execute('DROP SCHEMA manual_api')