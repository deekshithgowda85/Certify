"""group large submissions into queued jobs

Revision ID: 004
Revises: 003
"""
import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_job_batches_user_idempotency_key"
        ),
    )
    op.create_index("ix_job_batches_user_id", "job_batches", ["user_id"])
    op.add_column("jobs", sa.Column("batch_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_batch_id_job_batches", "jobs", "job_batches", ["batch_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_jobs_batch_id", "jobs", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_batch_id", table_name="jobs")
    op.drop_constraint("fk_jobs_batch_id_job_batches", "jobs", type_="foreignkey")
    op.drop_column("jobs", "batch_id")
    op.drop_index("ix_job_batches_user_id", table_name="job_batches")
    op.drop_table("job_batches")
