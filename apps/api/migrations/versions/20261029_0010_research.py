"""Private evaluation work and selected-region vectors."""

from alembic import op
from sqlalchemy import text

from bouquetbrowse.research_models import CropEmbedding, EvaluationDataset, EvaluationItem

revision = "20261029_0010"
down_revision = "20261029_0009"
branch_labels = None
depends_on = None
TABLES = [CropEmbedding.__table__, EvaluationDataset.__table__, EvaluationItem.__table__]


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
