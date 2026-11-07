"""Track research, generation, and independent QC states."""
from alembic import op
import sqlalchemy as sa

revision = "0002_pipeline_statuses"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("lessons")}
    columns = (
        ("research_status", "not_started"),
        ("generation_status", "not_started"),
        ("factual_qc_status", "not_started"),
        ("instructional_qc_status", "not_started"),
    )
    for name, default in columns:
        if name not in existing:
            op.add_column(
                "lessons",
                sa.Column(name, sa.String(24), nullable=False, server_default=default),
            )


def downgrade():
    op.drop_column("lessons", "instructional_qc_status")
    op.drop_column("lessons", "factual_qc_status")
    op.drop_column("lessons", "generation_status")
    op.drop_column("lessons", "research_status")
