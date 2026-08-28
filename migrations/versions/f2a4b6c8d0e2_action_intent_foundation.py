"""Action intent foundation

Revision ID: f2a4b6c8d0e2
Revises: e1f3a5c7d9b2
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a4b6c8d0e2"
down_revision: str | Sequence[str] | None = "e1f3a5c7d9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_intents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.String(length=240), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("risk", sa.String(length=40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("execution_scope", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected', 'expired')",
            name="ck_action_intent_status",
        ),
        sa.CheckConstraint(
            "execution_scope = 'single_use'",
            name="ck_action_intent_single_use_scope",
        ),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    for column, unique in (
        ("tenant_id", False),
        ("task_id", False),
        ("action_type", False),
        ("status", False),
        ("expires_at", False),
    ):
        op.create_index(
            op.f(f"ix_action_intents_{column}"),
            "action_intents",
            [column],
            unique=unique,
        )


def downgrade() -> None:
    for column in (
        "expires_at",
        "status",
        "action_type",
        "task_id",
        "tenant_id",
    ):
        op.drop_index(op.f(f"ix_action_intents_{column}"), table_name="action_intents")
    op.drop_table("action_intents")
