"""Restricted SQL entrypoint for queuing new soldier verification.

Revision ID: 0012_manual_verify_api
Revises: 0011_manual_verification
"""
from alembic import op

revision = "0012_manual_verify_api"
down_revision = "0011_manual_verification"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE FUNCTION manual_api.enqueue_soldier_verification(
      p_persona_id bigint, p_platform text, p_url text
    ) RETURNS bigint
    LANGUAGE plpgsql SECURITY INVOKER
    SET search_path = pg_catalog, pg_temp
    AS $function$
    DECLARE v_id bigint;
    BEGIN
      IF p_persona_id IS NULL OR p_persona_id <= 0
         OR p_platform NOT IN ('pc','ps4','xboxone')
         OR p_url IS NULL OR length(p_url) > 1024
         OR p_url NOT LIKE 'https://battlelog.battlefield.com/bf4/soldier/%'
      THEN RAISE EXCEPTION 'invalid verification request' USING ERRCODE = '22023';
      END IF;
      INSERT INTO public.manual_soldier_verifications
        (persona_id, platform, submitted_url, status, submitted_at)
      VALUES (p_persona_id, p_platform, p_url, 'pending', now())
      ON CONFLICT (persona_id, platform) DO UPDATE
      SET submitted_url = EXCLUDED.submitted_url,
          submitted_at = CASE WHEN public.manual_soldier_verifications.status = 'rejected'
              THEN now() ELSE public.manual_soldier_verifications.submitted_at END,
          status = CASE WHEN public.manual_soldier_verifications.status = 'rejected'
              THEN 'pending' ELSE public.manual_soldier_verifications.status END
      RETURNING verification_id INTO v_id;
      RETURN v_id;
    END
    $function$;
    REVOKE ALL ON FUNCTION manual_api.enqueue_soldier_verification(bigint,text,text) FROM PUBLIC;
    """)


def downgrade():
    op.execute("DROP FUNCTION IF EXISTS manual_api.enqueue_soldier_verification(bigint,text,text)")
