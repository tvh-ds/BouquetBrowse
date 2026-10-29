"""Ephemeral browser continuation and attributable profile observations."""

from alembic import op
from sqlalchemy import text

from bouquetbrowse.browser_models import BrowserObservation, ProfileSnapshot

revision = "20261029_0004"
down_revision = "20261029_0003"
branch_labels = None
depends_on = None
TABLES = [ProfileSnapshot.__table__, BrowserObservation.__table__]


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
