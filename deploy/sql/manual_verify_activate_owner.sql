-- Run after migrations 0011/0012 and the existing manual API owner setup.
BEGIN;
GRANT SELECT, INSERT, UPDATE ON public.manual_soldier_verifications TO bf4ps_manual_function_owner;
GRANT USAGE ON SEQUENCE public.manual_soldier_verifications_verification_id_seq TO bf4ps_manual_function_owner;
ALTER FUNCTION manual_api.enqueue_soldier_verification(bigint,text,text) OWNER TO bf4ps_manual_function_owner;
ALTER FUNCTION manual_api.enqueue_soldier_verification(bigint,text,text) SECURITY DEFINER;
REVOKE ALL ON FUNCTION manual_api.enqueue_soldier_verification(bigint,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION manual_api.enqueue_soldier_verification(bigint,text,text) TO bf4ps_manual_api;
COMMIT;
