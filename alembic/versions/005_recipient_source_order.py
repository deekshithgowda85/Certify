"""preserve input order within bulk batches

Revision ID: 005
Revises: 004
"""
import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipients", sa.Column("source_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipients", "source_index")
