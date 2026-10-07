"""persist idempotency data for job submissions

Revision ID: 003
Revises: 002
"""
import sqlalchemy as sa

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("valid_recipients", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "jobs",
        sa.Column("invalid_recipients", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("jobs", sa.Column("idempotency_key", sa.String(255), nullable=True))
    op.add_column("jobs", sa.Column("request_fingerprint", sa.String(64), nullable=True))
    op.add_column("jobs", sa.Column("enqueue_error", sa.Text(), nullable=True))
    op.create_unique_constraint(
        "uq_jobs_user_idempotency_key",
        "jobs",
        ["user_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_jobs_user_idempotency_key", "jobs", type_="unique")
    op.drop_column("jobs", "enqueue_error")
    op.drop_column("jobs", "request_fingerprint")
    op.drop_column("jobs", "idempotency_key")
    op.drop_column("jobs", "invalid_recipients")
    op.drop_column("jobs", "valid_recipients")
