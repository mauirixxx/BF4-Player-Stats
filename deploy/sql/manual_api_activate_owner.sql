-- Run ONLY as a PostgreSQL administrator, AFTER migration 0010, in the
-- intended database. No login, password, or HTTP endpoint is created here.
-- Run in one transaction; any missing privilege or object rolls back.
BEGIN;
DO $body$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='bf4ps_manual_function_owner') THEN
   CREATE ROLE bf4ps_manual_function_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
 END IF;
END
$body$;
GRANT USAGE ON SCHEMA public TO bf4ps_manual_function_owner;
GRANT USAGE ON SCHEMA manual_api TO bf4ps_manual_function_owner;
GRANT SELECT ON public.soldiers, public.collection_state, public.manual_request_cooldowns TO bf4ps_manual_function_owner;
GRANT SELECT, INSERT ON public.manual_collection_requests TO bf4ps_manual_function_owner;
GRANT INSERT, UPDATE ON public.manual_request_cooldowns TO bf4ps_manual_function_owner;
GRANT SELECT, INSERT, UPDATE ON public.collection_jobs TO bf4ps_manual_function_owner;
GRANT USAGE ON SEQUENCE public.manual_collection_requests_request_id_seq TO bf4ps_manual_function_owner;
GRANT USAGE ON SEQUENCE public.collection_jobs_job_id_seq TO bf4ps_manual_function_owner;
-- SELECT FOR UPDATE requires UPDATE on the locked columns, not just SELECT.
GRANT UPDATE (soldier_id) ON public.soldiers TO bf4ps_manual_function_owner;
GRANT UPDATE (soldier_id) ON public.manual_request_cooldowns TO bf4ps_manual_function_owner;
ALTER FUNCTION manual_api.request_existing_soldier(bigint,text,text)
 OWNER TO bf4ps_manual_function_owner;
ALTER FUNCTION manual_api.request_existing_soldier(bigint,text,text)
 SECURITY DEFINER;
REVOKE ALL ON FUNCTION manual_api.request_existing_soldier(bigint,text,text) FROM PUBLIC;
REVOKE ALL ON SCHEMA manual_api FROM PUBLIC;
COMMIT;