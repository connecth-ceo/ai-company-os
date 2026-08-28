"""Decision memory lifecycle

Revision ID: c9d1e3f5a7b9
Revises: b8c0d2e4f6a8
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d1e3f5a7b9"
down_revision: str | Sequence[str] | None = "b8c0d2e4f6a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("decisions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=40),
                nullable=False,
                server_default="active",
            )
        )
        batch_op.add_column(
            sa.Column(
                "scope",
                sa.String(length=40),
                nullable=False,
                server_default="company",
            )
        )
        batch_op.add_column(
            sa.Column(
                "applies_to",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(sa.Column("effective_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("review_due_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("supersedes_decision_id", sa.String(length=36)))

    op.execute(sa.text("UPDATE decisions SET effective_at = created_at"))

    with op.batch_alter_table("decisions") as batch_op:
        batch_op.alter_column("effective_at", nullable=False)
        batch_op.create_foreign_key(
            "fk_decisions_supersedes_decision_id_decisions",
            "decisions",
            ["supersedes_decision_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_unique_constraint(
            "uq_decisions_supersedes_decision_id",
            ["supersedes_decision_id"],
        )
        batch_op.create_check_constraint(
            "ck_decision_not_self_supersede",
            "supersedes_decision_id IS NULL OR supersedes_decision_id <> id",
        )
        batch_op.create_check_constraint(
            "ck_decision_status",
            "status IN ('proposed', 'active', 'superseded', 'expired', 'revoked')",
        )
        batch_op.create_check_constraint(
            "ck_decision_scope",
            "scope IN ('company', 'project', 'task', 'department')",
        )
        batch_op.create_index(op.f("ix_decisions_status"), ["status"])
        batch_op.create_index(op.f("ix_decisions_scope"), ["scope"])
        batch_op.create_index(op.f("ix_decisions_effective_at"), ["effective_at"])


def downgrade() -> None:
    with op.batch_alter_table("decisions") as batch_op:
        batch_op.drop_index(op.f("ix_decisions_effective_at"))
        batch_op.drop_index(op.f("ix_decisions_scope"))
        batch_op.drop_index(op.f("ix_decisions_status"))
        batch_op.drop_constraint("ck_decision_scope", type_="check")
        batch_op.drop_constraint("ck_decision_status", type_="check")
        batch_op.drop_constraint("ck_decision_not_self_supersede", type_="check")
        batch_op.drop_constraint("uq_decisions_supersedes_decision_id", type_="unique")
        batch_op.drop_constraint(
            "fk_decisions_supersedes_decision_id_decisions",
            type_="foreignkey",
        )
        batch_op.drop_column("supersedes_decision_id")
        batch_op.drop_column("review_due_at")
        batch_op.drop_column("expires_at")
        batch_op.drop_column("effective_at")
        batch_op.drop_column("applies_to")
        batch_op.drop_column("scope")
        batch_op.drop_column("status")
