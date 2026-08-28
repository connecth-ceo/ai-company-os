"""Commitment tracking

Revision ID: d0e2f4a6b8c1
Revises: c9d1e3f5a7b9
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0e2f4a6b8c1"
down_revision: str | Sequence[str] | None = "c9d1e3f5a7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "commitments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("owner_type", sa.String(length=40), nullable=False),
        sa.Column("owner_id", sa.String(length=100), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("decision_id", sa.String(length=36), nullable=True),
        sa.Column(
            "reminder_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'completed', 'cancelled')",
            name="ck_commitment_status",
        ),
        sa.CheckConstraint(
            "owner_type IN ('person', 'agent', 'team')",
            name="ck_commitment_owner_type",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'decision', 'task', 'meeting', 'external')",
            name="ck_commitment_source_type",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR "
            "(status <> 'completed' AND completed_at IS NULL)",
            name="ck_commitment_completion_consistency",
        ),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "tenant_id",
        "owner_type",
        "owner_id",
        "due_at",
        "status",
        "source_type",
        "project_id",
        "task_id",
        "decision_id",
    ):
        op.create_index(op.f(f"ix_commitments_{column}"), "commitments", [column])


def downgrade() -> None:
    for column in (
        "decision_id",
        "task_id",
        "project_id",
        "source_type",
        "status",
        "due_at",
        "owner_id",
        "owner_type",
        "tenant_id",
    ):
        op.drop_index(op.f(f"ix_commitments_{column}"), table_name="commitments")
    op.drop_table("commitments")
