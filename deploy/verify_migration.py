"""Verify migrated PostgreSQL controls in a disposable CI database only."""

from pathlib import Path
from uuid import uuid4

from bouquetbrowse import models  # noqa: F401
from bouquetbrowse.config import get_settings
from bouquetbrowse.db import Base
from bouquetbrowse.graphs import discovery_graph, invoke_graph, postgres_checkpointer
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

url = get_settings().database_url
if not (make_url(url).database or "").endswith("_test"):
    raise SystemExit("Use an isolated database ending _test.")
engine = create_engine(url)
with engine.begin() as connection:
    for table in Base.metadata.sorted_tables:
        enabled = connection.scalar(
            text(
                "SELECT rowsecurity FROM pg_tables WHERE schemaname='public' AND tablename=:name"
            ),
            {"name": table.name},
        )
        assert enabled, f"RLS missing: {table.name}"
    assert connection.scalar(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))
    assert connection.scalar(
        text("SELECT 1 FROM pg_indexes WHERE indexname='ix_listing_fts'")
    )
    connection.execute(text(Path(__file__).with_name("runtime-role.sql").read_text()))
with engine.begin() as connection:
    connection.execute(text("SET LOCAL ROLE bouquet_runtime"))
    connection.execute(text("SELECT id FROM listings LIMIT 1"))
    connection.execute(text("SELECT id FROM jobs LIMIT 1"))
    connection.execute(text("SELECT id FROM conversation_captures LIMIT 1"))
    connection.execute(text("SELECT id FROM offer_occurrences LIMIT 1"))
    connection.execute(text("SELECT id FROM graph_executions LIMIT 1"))
    connection.execute(text("SELECT id FROM model_calls LIMIT 1"))
    connection.execute(text("SELECT thread_id FROM graph_checkpoints.checkpoints LIMIT 1"))
    assert not connection.scalar(
        text("SELECT has_schema_privilege(current_user,'public','CREATE')")
    )


class CheckpointSmoke:
    def stage(self, name, state):
        return {"stop": True} if name == "select_task" else {}


with postgres_checkpointer(url) as saver:
    saver.conn.execute("SET ROLE bouquet_runtime")
    thread_id = str(uuid4())
    assert invoke_graph(discovery_graph(CheckpointSmoke(), saver), thread_id)["stop"]
    saver.delete_thread(thread_id)
print(
    "Migration RLS, vector/FTS indexes, runtime checkpoint writes and schema isolation verified."
)
