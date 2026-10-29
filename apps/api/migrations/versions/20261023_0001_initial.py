"""Initial evidence, catalog, observations, jobs and vector schema."""

from pathlib import Path
from runpy import run_path

from alembic import op
from sqlalchemy import text

Base = run_path(str(Path(__file__).parents[1] / "legacy_schema.py"))["Base"]

revision = "20261023_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("SET search_path TO public, extensions"))
    Base.metadata.create_all(connection)
    if connection.dialect.name == "postgresql":
        connection.execute(
            text("CREATE INDEX ix_listing_fts ON listings USING gin(to_tsvector('simple', search_text))")
        )
        # Runtime access is through FastAPI; raw/enrichment tables are not browser APIs.
        for table in Base.metadata.sorted_tables:
            connection.execute(text(f'REVOKE ALL ON TABLE "{table.name}" FROM PUBLIC'))
            connection.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))
        for role in ["anon", "authenticated"]:
            if connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}):
                for table in Base.metadata.sorted_tables:
                    connection.execute(text(f'REVOKE ALL ON TABLE "{table.name}" FROM "{role}"'))


def downgrade():
    Base.metadata.drop_all(op.get_bind())
