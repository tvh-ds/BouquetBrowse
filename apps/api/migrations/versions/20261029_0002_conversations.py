"""Neutral actors, conversation versions and stable offer identities."""

from alembic import op
from sqlalchemy import Column, String, text
from sqlalchemy.orm import Session

from bouquetbrowse import conversation_models
from bouquetbrowse.conversations import backfill_legacy
from bouquetbrowse.db import Base

revision = "20261029_0002"
down_revision = "20261023_0001"
branch_labels = None
depends_on = None

TABLES = tuple(
    table
    for table in Base.metadata.sorted_tables
    if table.name
    in {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__ == conversation_models.__name__
    }
)


def upgrade():
    with op.batch_alter_table("source_accounts") as batch:
        batch.alter_column("seller_id", existing_type=String(36), nullable=True)
        batch.add_column(Column("platform_account_id", String(160), nullable=True))
        batch.add_column(Column("role", String(24), nullable=False, server_default="unresolved"))
        batch.create_unique_constraint("uq_platform_account_id", ["platform", "platform_account_id"])
    with op.batch_alter_table("source_posts") as batch:
        from sqlalchemy import DateTime

        batch.alter_column("published_at", existing_type=DateTime(timezone=True), nullable=True)
    connection = op.get_bind()
    for table in TABLES:
        table.create(connection)
        if connection.dialect.name == "postgresql":
            connection.execute(text(f'REVOKE ALL ON TABLE "{table.name}" FROM PUBLIC'))
            connection.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))
            for role in ["anon", "authenticated"]:
                if connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}):
                    connection.execute(text(f'REVOKE ALL ON TABLE "{table.name}" FROM "{role}"'))
    with Session(bind=connection) as db:
        backfill_legacy(db)
        db.flush()


def downgrade():
    connection = op.get_bind()
    if connection.scalar(text("SELECT count(*) FROM source_accounts WHERE seller_id IS NULL")):
        raise RuntimeError("Cannot downgrade while neutral accounts exist; export or migrate them first")
    if connection.scalar(text("SELECT count(*) FROM source_posts WHERE published_at IS NULL")):
        raise RuntimeError("Cannot downgrade unknown publication dates")
    for table in reversed(TABLES):
        table.drop(connection)
    with op.batch_alter_table("source_posts") as batch:
        from sqlalchemy import DateTime

        batch.alter_column("published_at", existing_type=DateTime(timezone=True), nullable=False)
    with op.batch_alter_table("source_accounts") as batch:
        batch.drop_constraint("uq_platform_account_id", type_="unique")
        batch.drop_column("role")
        batch.drop_column("platform_account_id")
        batch.alter_column("seller_id", existing_type=String(36), nullable=False)
