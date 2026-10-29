"""Versioned visual evidence and model-category qualification."""

from alembic import op
from sqlalchemy import text

from bouquetbrowse.recognition_models import ImageRegion, RecognitionRecord, RecognitionSupport

revision = "20261029_0006"
down_revision = "20261029_0005"
branch_labels = None
depends_on = None
TABLES = [ImageRegion.__table__, RecognitionRecord.__table__, RecognitionSupport.__table__]


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
