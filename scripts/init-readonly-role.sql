-- Creates a read-only role used by the agent SQL tool (defense in depth).
-- Runs once on first Postgres init.
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lineageiq_ro') THEN
      CREATE ROLE lineageiq_ro LOGIN PASSWORD 'lineageiq_ro';
   END IF;
END
$$;

GRANT CONNECT ON DATABASE lineageiq TO lineageiq_ro;
GRANT USAGE ON SCHEMA public TO lineageiq_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO lineageiq_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO lineageiq_ro;
-- Explicitly no INSERT/UPDATE/DELETE/DDL granted.
