"""Briefing delivery tracking

Revision ID: e1f3a5c7d9b2
Revises: d0e2f4a6b8c1
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f3a5c7d9b2"
down_revision: str | Sequence[str] | None = "d0e2f4a6b8c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "briefing_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("briefing_date", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("dedupe_key", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'uncertain')",
            name="ck_briefing_delivery_status",
        ),
        sa.CheckConstraint(
            "(status = 'sent' AND sent_at IS NOT NULL) OR (status <> 'sent' AND sent_at IS NULL)",
            name="ck_briefing_delivery_sent_consistency",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_briefing_deliveries_dedupe_key"),
    )
    for column in (
        "tenant_id",
        "briefing_date",
        "channel",
        "status",
        "scheduled_for",
        "next_retry_at",
    ):
        op.create_index(
            op.f(f"ix_briefing_deliveries_{column}"),
            "briefing_deliveries",
            [column],
        )


def downgrade() -> None:
    for column in (
        "next_retry_at",
        "scheduled_for",
        "status",
        "channel",
        "briefing_date",
        "tenant_id",
    ):
        op.drop_index(
            op.f(f"ix_briefing_deliveries_{column}"),
            table_name="briefing_deliveries",
        )
    op.drop_table("briefing_deliveries")
