-- Run as database administrator in the intended database only AFTER 0010
-- and manual_api_activate_owner.sql. Creates an unusable LOGIN until an
-- administrator sets a secret out of band. Do not commit passwords.
BEGIN;
DO $body$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='bf4ps_manual_api') THEN
   CREATE ROLE bf4ps_manual_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
     NOREPLICATION NOINHERIT CONNECTION LIMIT 4;
 END IF;
END
$body$;
GRANT CONNECT ON DATABASE bf4_playerstats TO bf4ps_manual_api;
GRANT USAGE ON SCHEMA manual_api TO bf4ps_manual_api;
GRANT EXECUTE ON FUNCTION manual_api.request_existing_soldier(bigint,text,text)
 TO bf4ps_manual_api;
COMMIT;
-- Before service activation: set a random password with a secret-management
-- workflow and verify that has_table_privilege(...,'UPDATE') is false.