"""Execution receipt ledger

Revision ID: f0a2c4e6b8d0
Revises: e4f6a8b0c2d4
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f0a2c4e6b8d0"
down_revision: str | Sequence[str] | None = "e4f6a8b0c2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("execution_attempt_id", sa.String(length=36), nullable=False),
        sa.Column("connector_key", sa.String(length=80), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("outcome_code", sa.String(length=120), nullable=False),
        sa.Column("provider_reference_hash", sa.String(length=64), nullable=True),
        sa.Column("response_hash", sa.String(length=64), nullable=True),
        sa.Column("completed_by", sa.String(length=100), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'failed', 'uncertain')",
            name="ck_execution_receipt_outcome",
        ),
        sa.CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_execution_receipt_payload_hash_length",
        ),
        sa.CheckConstraint(
            "provider_reference_hash IS NULL OR length(provider_reference_hash) = 64",
            name="ck_execution_receipt_provider_reference_hash_length",
        ),
        sa.CheckConstraint(
            "response_hash IS NULL OR length(response_hash) = 64",
            name="ck_execution_receipt_response_hash_length",
        ),
        sa.CheckConstraint(
            "outcome <> 'succeeded' OR "
            "(provider_reference_hash IS NOT NULL AND response_hash IS NOT NULL)",
            name="ck_execution_receipt_success_proof",
        ),
        sa.CheckConstraint(
            "(provider_reference_hash IS NULL AND response_hash IS NULL) OR "
            "(provider_reference_hash IS NOT NULL AND response_hash IS NOT NULL)",
            name="ck_execution_receipt_proof_pair",
        ),
        sa.ForeignKeyConstraint(
            ["execution_attempt_id"],
            ["execution_attempts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_attempt_id",
            name="uq_execution_receipt_execution_attempt",
        ),
    )
    for column in (
        "action_type",
        "connector_key",
        "execution_attempt_id",
        "outcome",
        "tenant_id",
    ):
        op.create_index(
            op.f(f"ix_execution_receipts_{column}"),
            "execution_receipts",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("execution_receipts")
