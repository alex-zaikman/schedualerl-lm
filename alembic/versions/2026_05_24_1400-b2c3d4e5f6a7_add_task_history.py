"""add task_history with RLS

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-24 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("trigger_type", sa.String(length=32), nullable=True),
        sa.Column("cron_expression", sa.String(), nullable=True),
        sa.Column("cron_timezone", sa.String(), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("once_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_source", sa.String(length=16), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            """
            (
                event_type IN ('task_created', 'task_deleted')
                AND webhook_url IS NOT NULL
                AND trigger_type IS NOT NULL
                AND execution_source IS NULL
                AND http_status IS NULL
                AND error_message IS NULL
                AND success IS NULL
                AND (
                    (
                        trigger_type = 'cron'
                        AND cron_expression IS NOT NULL
                        AND cron_timezone IS NOT NULL
                        AND interval_seconds IS NULL
                        AND once_run_at IS NULL
                    )
                    OR (
                        trigger_type = 'interval'
                        AND interval_seconds IS NOT NULL
                        AND cron_expression IS NULL
                        AND cron_timezone IS NULL
                        AND once_run_at IS NULL
                    )
                    OR (
                        trigger_type = 'once'
                        AND once_run_at IS NOT NULL
                        AND cron_expression IS NULL
                        AND cron_timezone IS NULL
                        AND interval_seconds IS NULL
                    )
                )
            )
            OR (
                event_type IN ('task_activated', 'task_deactivated')
                AND webhook_url IS NULL
                AND trigger_type IS NULL
                AND cron_expression IS NULL
                AND cron_timezone IS NULL
                AND interval_seconds IS NULL
                AND once_run_at IS NULL
                AND execution_source IS NULL
                AND http_status IS NULL
                AND error_message IS NULL
                AND success IS NULL
            )
            OR (
                event_type = 'execution'
                AND webhook_url IS NOT NULL
                AND execution_source IS NOT NULL
                AND success IS NOT NULL
                AND trigger_type IS NULL
                AND cron_expression IS NULL
                AND cron_timezone IS NULL
                AND interval_seconds IS NULL
                AND once_run_at IS NULL
                AND (
                    success = false
                    OR http_status IS NOT NULL
                )
            )
            """,
            name="task_history_event_shape",
        ),
    )
    op.create_index(op.f("ix_task_history_user_id"), "task_history", ["user_id"], unique=False)
    op.create_index(op.f("ix_task_history_task_id"), "task_history", ["task_id"], unique=False)
    op.create_index(
        "ix_task_history_user_id_created_at",
        "task_history",
        ["user_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_task_history_task_id_created_at",
        "task_history",
        ["task_id", sa.text("created_at DESC")],
        unique=False,
    )

    op.execute("ALTER TABLE task_history ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE task_history FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY task_history_user_select ON task_history
          FOR SELECT
          USING (user_id = current_setting('app.current_user_id', true))
        """
    )
    op.execute(
        """
        CREATE POLICY task_history_user_insert ON task_history
          FOR INSERT
          WITH CHECK (user_id = current_setting('app.current_user_id', true))
        """
    )
    op.execute(
        """
        CREATE POLICY task_history_scheduler_insert ON task_history
          FOR INSERT
          WITH CHECK (current_setting('app.is_scheduler', true) = 'true')
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_task_history_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'task_history is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER task_history_no_update
          BEFORE UPDATE OR DELETE ON task_history
          FOR EACH ROW EXECUTE FUNCTION prevent_task_history_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS task_history_no_update ON task_history")
    op.execute("DROP FUNCTION IF EXISTS prevent_task_history_mutation()")
    op.execute("DROP POLICY IF EXISTS task_history_scheduler_insert ON task_history")
    op.execute("DROP POLICY IF EXISTS task_history_user_insert ON task_history")
    op.execute("DROP POLICY IF EXISTS task_history_user_select ON task_history")
    op.drop_index("ix_task_history_task_id_created_at", table_name="task_history")
    op.drop_index("ix_task_history_user_id_created_at", table_name="task_history")
    op.drop_index(op.f("ix_task_history_task_id"), table_name="task_history")
    op.drop_index(op.f("ix_task_history_user_id"), table_name="task_history")
    op.drop_table("task_history")
