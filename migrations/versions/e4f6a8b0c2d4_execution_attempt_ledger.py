"""Execution attempt ledger

Revision ID: e4f6a8b0c2d4
Revises: d2f4a6b8c0e2
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4f6a8b0c2d4"
down_revision: str | Sequence[str] | None = "d2f4a6b8c0e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("action_intents") as batch_op:
        batch_op.drop_constraint("ck_action_intent_status", type_="check")
        batch_op.create_check_constraint(
            "ck_action_intent_status",
            "status IN ('proposed', 'approved', 'rejected', 'expired', 'consumed')",
        )

    op.create_table(
        "execution_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("action_intent_id", sa.String(length=36), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("connector_key", sa.String(length=80), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(length=100), nullable=False),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('prepared', 'claimed', 'succeeded', 'failed', 'uncertain')",
            name="ck_execution_attempt_status",
        ),
        sa.CheckConstraint(
            "timeout_seconds >= 5 AND timeout_seconds <= 900",
            name="ck_execution_attempt_timeout",
        ),
        sa.CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_execution_attempt_payload_hash_length",
        ),
        sa.CheckConstraint(
            "(claimed_at IS NULL AND claimed_by IS NULL) OR "
            "(claimed_at IS NOT NULL AND claimed_by IS NOT NULL)",
            name="ck_execution_attempt_claim_identity",
        ),
        sa.CheckConstraint(
            "(status = 'prepared' AND claimed_at IS NULL AND deadline_at IS NULL "
            "AND completed_at IS NULL) OR "
            "(status = 'claimed' AND claimed_at IS NOT NULL AND deadline_at IS NOT NULL "
            "AND completed_at IS NULL) OR "
            "(status IN ('succeeded', 'failed', 'uncertain') AND completed_at IS NOT NULL)",
            name="ck_execution_attempt_state_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["action_intent_id"],
            ["action_intents.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_intent_id", name="uq_execution_attempt_action_intent"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    for column in (
        "action_intent_id",
        "action_type",
        "approval_id",
        "connector_key",
        "status",
        "tenant_id",
    ):
        op.create_index(
            op.f(f"ix_execution_attempts_{column}"),
            "execution_attempts",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("execution_attempts")
    with op.batch_alter_table("action_intents") as batch_op:
        batch_op.drop_constraint("ck_action_intent_status", type_="check")
        batch_op.create_check_constraint(
            "ck_action_intent_status",
            "status IN ('proposed', 'approved', 'rejected', 'expired')",
        )
