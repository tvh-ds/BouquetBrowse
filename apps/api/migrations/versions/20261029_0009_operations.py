"""Durable local schedule, health and content-free deletion replay."""

from alembic import op
from sqlalchemy import text

from bouquetbrowse.operations_models import CallDependency, DeletionRecord, RuntimeStatus, ScheduleSlot

revision = "20261029_0009"
down_revision = "20261029_0008"
branch_labels = None
depends_on = None
TABLES = [ScheduleSlot.__table__, RuntimeStatus.__table__, DeletionRecord.__table__, CallDependency.__table__]


def upgrade():
    connection = op.get_bind()
    for table in TABLES:
        table.create(connection)
        if connection.dialect.name == "postgresql":
            connection.execute(text(f'REVOKE ALL ON TABLE "{table.name}" FROM PUBLIC'))
            connection.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))
            for role in ["anon", "authenticated"]:
                if connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}):
                    connection.execute(text(f'REVOKE ALL ON TABLE "{table.name}" FROM "{role}"'))


def downgrade():
    for table in reversed(TABLES):
        table.drop(op.get_bind())
