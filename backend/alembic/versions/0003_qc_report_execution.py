"""Add QC execution identity and uniqueness."""
from alembic import op
import sqlalchemy as sa

revision = "0003_qc_report_execution"
down_revision = "0002_pipeline_statuses"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("qc_reports", sa.Column("execution_id", sa.String(length=36), nullable=True))
    op.create_index("ix_qc_reports_execution_id", "qc_reports", ["execution_id"])
    op.create_unique_constraint(
        "uq_qc_report_execution", "qc_reports",
        ["lesson_id", "kind", "execution_id"],
    )


def downgrade():
    op.drop_constraint("uq_qc_report_execution", "qc_reports", type_="unique")
    op.drop_index("ix_qc_reports_execution_id", table_name="qc_reports")
    op.drop_column("qc_reports", "execution_id")
