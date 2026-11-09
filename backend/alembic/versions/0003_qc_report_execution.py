"""Add QC execution identity and uniqueness."""
from alembic import op
import sqlalchemy as sa

revision = "0003_qc_report_execution"
down_revision = "0002_pipeline_statuses"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("qc_reports")}
    if "execution_id" not in columns:
        op.add_column(
            "qc_reports",
            sa.Column("execution_id", sa.String(length=36), nullable=True),
        )

    indexes = {index["name"] for index in inspector.get_indexes("qc_reports")}
    if "ix_qc_reports_execution_id" not in indexes:
        op.create_index(
            "ix_qc_reports_execution_id",
            "qc_reports",
            ["execution_id"],
        )

    constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("qc_reports")
    }
    if "uq_qc_report_execution" not in constraints:
        op.create_unique_constraint(
            "uq_qc_report_execution",
            "qc_reports",
            ["lesson_id", "kind", "execution_id"],
        )


def downgrade():
    op.drop_constraint("uq_qc_report_execution", "qc_reports", type_="unique")
    op.drop_index("ix_qc_reports_execution_id", table_name="qc_reports")
    op.drop_column("qc_reports", "execution_id")
