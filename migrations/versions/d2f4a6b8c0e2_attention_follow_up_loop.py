"""Attention follow-up loop

Revision ID: d2f4a6b8c0e2
Revises: a7c9e1f3b5d7
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2f4a6b8c0e2"
down_revision: str | Sequence[str] | None = "a7c9e1f3b5d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attention_follow_ups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("attention_id", sa.String(length=160), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("commitment_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["commitment_id"],
            ["commitments.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("commitment_id"),
        sa.UniqueConstraint("task_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
        sa.UniqueConstraint(
            "tenant_id",
            "attention_id",
            "fingerprint",
            name="uq_attention_follow_ups_signal",
        ),
    )
    for column in (
        "attention_id",
        "commitment_id",
        "fingerprint",
        "task_id",
        "tenant_id",
    ):
        op.create_index(
            op.f(f"ix_attention_follow_ups_{column}"),
            "attention_follow_ups",
            [column],
            unique=column in {"commitment_id", "task_id"},
        )


def downgrade() -> None:
    op.drop_table("attention_follow_ups")
