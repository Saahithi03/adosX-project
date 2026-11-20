#!/bin/sh
# Runs once, on the first start of an empty data volume (postgres image
# convention). To re-run it: `make db-reset`.
#
# Creates the two roles the project uses:
#   dealeros_owner  owns the schema and tables; runs migrations and ingest.
#   dealeros_app    the web app and the tests. Not an owner, not a superuser,
#                   no BYPASSRLS, so row-level security always applies to it.
set -eu

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v db="$POSTGRES_DB" \
     -v owner_pw="$DEALEROS_OWNER_PASSWORD" \
     -v app_pw="$DEALEROS_APP_PASSWORD" <<'SQL'
-- Both roles are explicitly stripped of every attribute that skips RLS.
-- NOBYPASSRLS on the owner is least-privilege for now. How ingest writes
-- rows for every org under FORCE RLS is decided in step 2 (DECISIONS.md).
CREATE ROLE dealeros_owner LOGIN PASSWORD :'owner_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE dealeros_app LOGIN PASSWORD :'app_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- The owner role owns the database and the public schema, so every table
-- Django's migrations create belongs to it.
ALTER DATABASE :"db" OWNER TO dealeros_owner;
ALTER SCHEMA public OWNER TO dealeros_owner;

-- Nobody else gets in by default.
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- The app role may connect and use the schema, but cannot create objects.
GRANT CONNECT ON DATABASE :"db" TO dealeros_app;
GRANT USAGE ON SCHEMA public TO dealeros_app;

-- Every table/sequence the owner creates later (i.e. via migrations) is
-- automatically readable and writable by the app role. DML only: the app
-- can never ALTER, DROP, or disable RLS on a table, because it doesn't own it.
ALTER DEFAULT PRIVILEGES FOR ROLE dealeros_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dealeros_app;
ALTER DEFAULT PRIVILEGES FOR ROLE dealeros_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO dealeros_app;
SQL
