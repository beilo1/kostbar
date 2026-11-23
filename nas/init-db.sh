#!/bin/sh
# Runs only when the official PostgreSQL image initializes an empty data volume.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_password="$KASSE_DB_PASSWORD" <<'SQL'
CREATE ROLE kaffeekasse LOGIN PASSWORD :'app_password';
ALTER DATABASE kaffeekasse OWNER TO kaffeekasse;
SQL
