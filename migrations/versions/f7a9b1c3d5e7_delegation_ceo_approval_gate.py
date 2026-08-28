"""delegation CEO approval gate

Revision ID: f7a9b1c3d5e7
Revises: e6f8a0c2d4b6
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a9b1c3d5e7"
down_revision: str | Sequence[str] | None = "e6f8a0c2d4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("delegations") as batch_op:
        batch_op.add_column(sa.Column("approval_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_delegations_approval_id_approvals",
            "approvals",
            ["approval_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(op.f("ix_delegations_approval_id"), ["approval_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("delegations") as batch_op:
        batch_op.drop_index(op.f("ix_delegations_approval_id"))
        batch_op.drop_constraint("fk_delegations_approval_id_approvals", type_="foreignkey")
        batch_op.drop_column("approval_id")
