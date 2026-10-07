"""initial schema: jobs and recipients

Revision ID: 001
Revises:
Create Date: 2024-10-01 10:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("processing_mode", sa.String(10), nullable=True),
        sa.Column("total_recipients", sa.Integer(), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("container_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "recipients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("course_name", sa.String(255), nullable=False),
        sa.Column("completion_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("certificate_path", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_recipients_job_id", "recipients", ["job_id"])
    op.create_index("ix_recipients_job_id_status", "recipients", ["job_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_recipients_job_id_status", table_name="recipients")
    op.drop_index("ix_recipients_job_id", table_name="recipients")
    op.drop_table("recipients")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
