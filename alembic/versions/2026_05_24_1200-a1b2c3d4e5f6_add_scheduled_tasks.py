"""add scheduled_tasks with RLS

Revision ID: a1b2c3d4e5f6
Revises: ea41e048fbe5
Create Date: 2026-05-24 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "ea41e048fbe5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scheduled_tasks_user_id"), "scheduled_tasks", ["user_id"], unique=False)

    op.execute("ALTER TABLE scheduled_tasks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheduled_tasks FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY scheduled_tasks_user_all ON scheduled_tasks
          FOR ALL
          USING (user_id = current_setting('app.current_user_id', true))
          WITH CHECK (user_id = current_setting('app.current_user_id', true))
        """
    )
    op.execute(
        """
        CREATE POLICY scheduled_tasks_scheduler ON scheduled_tasks
          FOR ALL
          USING (current_setting('app.is_scheduler', true) = 'true')
          WITH CHECK (current_setting('app.is_scheduler', true) = 'true')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS scheduled_tasks_scheduler ON scheduled_tasks")
    op.execute("DROP POLICY IF EXISTS scheduled_tasks_user_all ON scheduled_tasks")
    op.drop_index(op.f("ix_scheduled_tasks_user_id"), table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
