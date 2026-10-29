"""Content-free alerts and durable notification versions."""

from alembic import op
from sqlalchemy import text

from bouquetbrowse.maintenance_models import OperationAlert

revision = "20261029_0011"
down_revision = "20261029_0010"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    OperationAlert.__table__.create(connection)
    if connection.dialect.name == "postgresql":
        connection.execute(text("REVOKE ALL ON TABLE operation_alerts FROM PUBLIC"))
        connection.execute(text("ALTER TABLE operation_alerts ENABLE ROW LEVEL SECURITY"))
        for role in ["anon", "authenticated"]:
            if connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}):
                connection.execute(text(f'REVOKE ALL ON TABLE operation_alerts FROM "{role}"'))


def downgrade():
    OperationAlert.__table__.drop(op.get_bind())
