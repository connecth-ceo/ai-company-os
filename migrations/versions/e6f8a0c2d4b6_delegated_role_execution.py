"""delegated role execution ledger

Revision ID: e6f8a0c2d4b6
Revises: d4e6a8b0c2f4
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6f8a0c2d4b6"
down_revision: str | Sequence[str] | None = "d4e6a8b0c2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("delegations") as batch_op:
        batch_op.add_column(sa.Column("task_run_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("runtime_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("provider", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("model", sa.String(length=160), nullable=True))
        batch_op.add_column(
            sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("error", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_delegations_task_run_id_task_runs",
            "task_runs",
            ["task_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(op.f("ix_delegations_task_run_id"), ["task_run_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("delegations") as batch_op:
        batch_op.drop_index(op.f("ix_delegations_task_run_id"))
        batch_op.drop_constraint("fk_delegations_task_run_id_task_runs", type_="foreignkey")
        for name in (
            "error",
            "finished_at",
            "started_at",
            "duration_ms",
            "total_tokens",
            "output_tokens",
            "input_tokens",
            "model",
            "provider",
            "runtime_name",
            "task_run_id",
        ):
            batch_op.drop_column(name)
