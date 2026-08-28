"""delegation guardrails

Revision ID: d4e6a8b0c2f4
Revises: 8c2e4f6a9b10
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e6a8b0c2f4"
down_revision: str | Sequence[str] | None = "8c2e4f6a9b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delegations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("parent_task_id", sa.String(length=36), nullable=False),
        sa.Column("child_task_id", sa.String(length=36), nullable=False),
        sa.Column("initiator", sa.String(length=100), nullable=False),
        sa.Column("delegated_role", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("token_budget", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("cost_budget_usd", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["child_task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("child_task_id"),
    )
    op.create_index(
        op.f("ix_delegations_child_task_id"), "delegations", ["child_task_id"], unique=False
    )
    op.create_index(
        op.f("ix_delegations_delegated_role"),
        "delegations",
        ["delegated_role"],
        unique=False,
    )
    op.create_index(op.f("ix_delegations_parent_task_id"), "delegations", ["parent_task_id"])
    op.create_index(op.f("ix_delegations_project_id"), "delegations", ["project_id"])
    op.create_index(op.f("ix_delegations_status"), "delegations", ["status"])
    op.create_index(op.f("ix_delegations_tenant_id"), "delegations", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_delegations_tenant_id"), table_name="delegations")
    op.drop_index(op.f("ix_delegations_status"), table_name="delegations")
    op.drop_index(op.f("ix_delegations_project_id"), table_name="delegations")
    op.drop_index(op.f("ix_delegations_parent_task_id"), table_name="delegations")
    op.drop_index(op.f("ix_delegations_delegated_role"), table_name="delegations")
    op.drop_index(op.f("ix_delegations_child_task_id"), table_name="delegations")
    op.drop_table("delegations")
