"""Provenance review foundation

Revision ID: c5e7f9b1d3a5
Revises: b4d6f8a0c2e4
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5e7f9b1d3a5"
down_revision: str | Sequence[str] | None = "b4d6f8a0c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provenance_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("provenance_record_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("previous_status", sa.String(length=40), nullable=False),
        sa.Column("reviewed_content_hash", sa.String(length=64), nullable=False),
        sa.Column("reviewed_by", sa.String(length=100), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('verified', 'rejected')",
            name="ck_provenance_review_decision",
        ),
        sa.CheckConstraint(
            "previous_status IN ('unverified', 'observed', 'verified', 'rejected')",
            name="ck_provenance_review_previous_status",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_record_id"],
            ["provenance_records.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    for column in (
        "decision",
        "provenance_record_id",
        "reviewed_content_hash",
        "tenant_id",
    ):
        op.create_index(
            op.f(f"ix_provenance_reviews_{column}"),
            "provenance_reviews",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("provenance_reviews")
