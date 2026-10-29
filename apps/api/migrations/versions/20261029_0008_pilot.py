"""Audited pilot proof summaries; no raw annotations in release tables."""

from alembic import op
from sqlalchemy import text

from bouquetbrowse.pilot_models import PilotProof

revision = "20261029_0008"
down_revision = "20261029_0007"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    PilotProof.__table__.create(connection)
    if connection.dialect.name == "postgresql":
        connection.execute(text("REVOKE ALL ON TABLE pilot_proofs FROM PUBLIC"))
        connection.execute(text("ALTER TABLE pilot_proofs ENABLE ROW LEVEL SECURITY"))
        for role in ["anon", "authenticated"]:
            if connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}):
                connection.execute(text(f'REVOKE ALL ON TABLE pilot_proofs FROM "{role}"'))


def downgrade():
    PilotProof.__table__.drop(op.get_bind())
