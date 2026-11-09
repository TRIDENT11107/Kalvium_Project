"""add instructor full name"""
from alembic import op
import sqlalchemy as sa

revision = "0004_user_full_name"
down_revision = "0003_qc_report_execution"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("full_name", sa.String(length=160), nullable=False, server_default=""))
    op.alter_column("users", "full_name", server_default=None)


def downgrade():
    op.drop_column("users", "full_name")
