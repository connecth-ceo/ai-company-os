"""Provenance foundation

Revision ID: b4d6f8a0c2e4
Revises: a3c5e7f9b1d3
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4d6f8a0c2e4"
down_revision: str | Sequence[str] | None = "a3c5e7f9b1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provenance_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("knowledge_item_id", sa.String(length=36), nullable=True),
        sa.Column("decision_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("task_run_id", sa.String(length=36), nullable=True),
        sa.Column("source_record_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_uri", sa.String(length=2048), nullable=True),
        sa.Column("source_label", sa.String(length=240), nullable=False),
        sa.Column("claim_reference", sa.String(length=240), nullable=True),
        sa.Column("produced_by_agent", sa.String(length=100), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("verification_status", sa.String(length=40), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "subject_type IN ('knowledge', 'decision')",
            name="ck_provenance_subject_type",
        ),
        sa.CheckConstraint(
            "source_type IN ('url', 'task_run', 'manual', 'inherited')",
            name="ck_provenance_source_type",
        ),
        sa.CheckConstraint(
            "verification_status IN ('unverified', 'observed', 'verified', 'rejected')",
            name="ck_provenance_verification_status",
        ),
        sa.CheckConstraint(
            "(subject_type = 'knowledge' AND knowledge_item_id IS NOT NULL "
            "AND decision_id IS NULL) OR "
            "(subject_type = 'decision' AND decision_id IS NOT NULL "
            "AND knowledge_item_id IS NULL)",
            name="ck_provenance_subject_reference",
        ),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["knowledge_item_id"], ["knowledge_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_record_id"], ["provenance_records.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_run_id"], ["task_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    for column in (
        "captured_at",
        "content_hash",
        "decision_id",
        "knowledge_item_id",
        "source_record_id",
        "source_type",
        "subject_type",
        "task_id",
        "task_run_id",
        "tenant_id",
        "verification_status",
    ):
        op.create_index(
            op.f(f"ix_provenance_records_{column}"),
            "provenance_records",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("provenance_records")
