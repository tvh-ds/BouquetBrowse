"""Application-owned graph execution, cost receipts and fenced jobs."""

from alembic import op
from sqlalchemy import BigInteger, Column, DateTime, String, text

from bouquetbrowse import runtime_models
from bouquetbrowse.db import Base

revision = "20261029_0003"
down_revision = "20261029_0002"
branch_labels = None
depends_on = None

TABLES = tuple(
    table
    for table in Base.metadata.sorted_tables
    if table.name
    in {m.local_table.name for m in Base.registry.mappers if m.class_.__module__ == runtime_models.__name__}
)


def upgrade():
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(Column("lease_token", String(36), nullable=True))
        batch.add_column(Column("cancelled_at", DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("cost_entries") as batch:
        batch.add_column(Column("amount_microusd", BigInteger, nullable=False, server_default="0"))
    connection = op.get_bind()
    connection.execute(text("UPDATE cost_entries SET amount_microusd=CAST(ROUND(amount_usd*1000000) AS BIGINT)"))
    for table in TABLES:
        table.create(connection)
        if connection.dialect.name == "postgresql":
            connection.execute(text(f'REVOKE ALL ON TABLE "{table.name}" FROM PUBLIC'))
            connection.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))
            for role in ["anon", "authenticated"]:
                if connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}):
                    connection.execute(text(f'REVOKE ALL ON TABLE "{table.name}" FROM "{role}"'))


def downgrade():
    connection = op.get_bind()
    for table in reversed(TABLES):
        table.drop(connection)
    with op.batch_alter_table("cost_entries") as batch:
        batch.drop_column("amount_microusd")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("cancelled_at")
        batch.drop_column("lease_token")
