"""AI cost ledger and monthly budget

Revision ID: b8c0d2e4f6a8
Revises: f7a9b1c3d5e7
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c0d2e4f6a8"
down_revision: str | Sequence[str] | None = "f7a9b1c3d5e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("delegations") as batch_op:
        batch_op.add_column(sa.Column("pricing_version", sa.String(length=80), nullable=True))
        batch_op.add_column(
            sa.Column(
                "estimated_max_cost_usd",
                sa.Numeric(precision=14, scale=8),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "reserved_cost_usd",
                sa.Numeric(precision=14, scale=8),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("cost_reservation_period_start", sa.Date(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "actual_estimated_cost_usd",
                sa.Numeric(precision=14, scale=8),
                nullable=True,
            )
        )

    op.create_table(
        "ai_monthly_budgets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("budget_usd", sa.Numeric(precision=14, scale=8), nullable=False),
        sa.Column(
            "reserved_usd", sa.Numeric(precision=14, scale=8), nullable=False, server_default="0"
        ),
        sa.Column(
            "estimated_spend_usd",
            sa.Numeric(precision=14, scale=8),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "uncertain_spend_usd",
            sa.Numeric(precision=14, scale=8),
            nullable=False,
            server_default="0",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("budget_usd >= 0", name="ck_ai_monthly_budget_nonnegative"),
        sa.CheckConstraint("reserved_usd >= 0", name="ck_ai_monthly_reserved_nonnegative"),
        sa.CheckConstraint(
            "estimated_spend_usd >= 0", name="ck_ai_monthly_estimated_spend_nonnegative"
        ),
        sa.CheckConstraint(
            "uncertain_spend_usd >= 0", name="ck_ai_monthly_uncertain_spend_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "provider", "period_start"),
    )
    op.create_index(
        op.f("ix_ai_monthly_budgets_tenant_id"), "ai_monthly_budgets", ["tenant_id"]
    )
    op.create_index(op.f("ix_ai_monthly_budgets_provider"), "ai_monthly_budgets", ["provider"])
    op.create_index(
        op.f("ix_ai_monthly_budgets_period_start"),
        "ai_monthly_budgets",
        ["period_start"],
    )

    op.create_table(
        "ai_cost_ledger",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("delegation_id", sa.String(length=36), nullable=False),
        sa.Column("task_run_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("pricing_version", sa.String(length=80), nullable=False),
        sa.Column("calculation_status", sa.String(length=40), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "input_rate_per_million_usd", sa.Numeric(precision=14, scale=8), nullable=False
        ),
        sa.Column(
            "output_rate_per_million_usd", sa.Numeric(precision=14, scale=8), nullable=False
        ),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=14, scale=8), nullable=False),
        sa.Column(
            "provider_billed_cost_usd", sa.Numeric(precision=14, scale=8), nullable=True
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("input_tokens >= 0", name="ck_ai_cost_input_tokens_nonnegative"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_ai_cost_output_tokens_nonnegative"),
        sa.CheckConstraint("total_tokens >= 0", name="ck_ai_cost_total_tokens_nonnegative"),
        sa.CheckConstraint("estimated_cost_usd >= 0", name="ck_ai_cost_estimate_nonnegative"),
        sa.ForeignKeyConstraint(
            ["delegation_id"], ["delegations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_run_id"], ["task_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delegation_id"),
        sa.UniqueConstraint("task_run_id"),
    )
    for column in (
        "tenant_id",
        "delegation_id",
        "task_run_id",
        "provider",
        "model",
        "calculation_status",
    ):
        op.create_index(op.f(f"ix_ai_cost_ledger_{column}"), "ai_cost_ledger", [column])


def downgrade() -> None:
    for column in (
        "calculation_status",
        "model",
        "provider",
        "task_run_id",
        "delegation_id",
        "tenant_id",
    ):
        op.drop_index(op.f(f"ix_ai_cost_ledger_{column}"), table_name="ai_cost_ledger")
    op.drop_table("ai_cost_ledger")
    op.drop_index(op.f("ix_ai_monthly_budgets_period_start"), table_name="ai_monthly_budgets")
    op.drop_index(op.f("ix_ai_monthly_budgets_provider"), table_name="ai_monthly_budgets")
    op.drop_index(op.f("ix_ai_monthly_budgets_tenant_id"), table_name="ai_monthly_budgets")
    op.drop_table("ai_monthly_budgets")
    with op.batch_alter_table("delegations") as batch_op:
        batch_op.drop_column("actual_estimated_cost_usd")
        batch_op.drop_column("cost_reservation_period_start")
        batch_op.drop_column("reserved_cost_usd")
        batch_op.drop_column("estimated_max_cost_usd")
        batch_op.drop_column("pricing_version")
