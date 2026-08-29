"""goal and project hierarchy foundation

Revision ID: a3c5e7f9b1d3
Revises: f2a4b6c8d0e2
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c5e7f9b1d3"
down_revision: str | Sequence[str] | None = "f2a4b6c8d0e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("success_metric", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(length=160), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_goals_status"), "goals", ["status"], unique=False)
    op.create_index(op.f("ix_goals_tenant_id"), "goals", ["tenant_id"], unique=False)

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("goal_id", sa.String(length=36), nullable=True))
        batch_op.create_index(op.f("ix_projects_goal_id"), ["goal_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_projects_goal_id_goals",
            "goals",
            ["goal_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("fk_projects_goal_id_goals", type_="foreignkey")
        batch_op.drop_index(op.f("ix_projects_goal_id"))
        batch_op.drop_column("goal_id")

    op.drop_index(op.f("ix_goals_tenant_id"), table_name="goals")
    op.drop_index(op.f("ix_goals_status"), table_name="goals")
    op.drop_table("goals")
