"""Attention acknowledgement history

Revision ID: a7c9e1f3b5d7
Revises: c5e7f9b1d3a5
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c9e1f3b5d7"
down_revision: str | Sequence[str] | None = "c5e7f9b1d3a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attention_acknowledgements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("attention_id", sa.String(length=160), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=80), nullable=False),
        sa.Column("acknowledged_by", sa.String(length=100), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "level IN ('info', 'watch', 'action', 'decision', 'critical')",
            name="ck_attention_acknowledgement_level",
        ),
        sa.CheckConstraint(
            "kind IN ('overdue_commitment', 'long_running_task', 'task_failure', "
            "'pending_approval', 'decision_governance')",
            name="ck_attention_acknowledgement_kind",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
        sa.UniqueConstraint(
            "tenant_id",
            "attention_id",
            "fingerprint",
            name="uq_attention_acknowledgements_signal",
        ),
    )
    for column in (
        "attention_id",
        "fingerprint",
        "kind",
        "level",
        "resource_id",
        "tenant_id",
    ):
        op.create_index(
            op.f(f"ix_attention_acknowledgements_{column}"),
            "attention_acknowledgements",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("attention_acknowledgements")
