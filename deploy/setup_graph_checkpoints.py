"""Run explicitly as migration owner after Alembic, never from API/worker startup."""

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from bouquetbrowse.config import get_settings

settings = get_settings()
if not settings.database_url.startswith("postgresql"):
    raise SystemExit("PostgreSQL is required for durable agent execution.")
url = make_url(settings.database_url).set(drivername="postgresql").render_as_string(hide_password=False)
with psycopg.connect(url, autocommit=True, prepare_threshold=0, row_factory=dict_row) as connection:
    connection.execute("CREATE SCHEMA IF NOT EXISTS graph_checkpoints")
    connection.execute("REVOKE ALL ON SCHEMA graph_checkpoints FROM PUBLIC")
    connection.execute("SET search_path TO graph_checkpoints")
    PostgresSaver(connection).setup()
    for table in ["checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"]:
        connection.execute(psycopg.sql.SQL("REVOKE ALL ON TABLE {} FROM PUBLIC").format(psycopg.sql.Identifier(table)))
        connection.execute(psycopg.sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(psycopg.sql.Identifier(table)))
        for role in ["anon", "authenticated"]:
            if connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                connection.execute(psycopg.sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(
                    psycopg.sql.Identifier(table), psycopg.sql.Identifier(role)))
print("Private graph checkpoints initialized; apply runtime-role.sql afterward.")
