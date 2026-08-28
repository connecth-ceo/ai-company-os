"""workflow recording layer

Revision ID: 8c2e4f6a9b10
Revises: 5f42d0b8a1c3
Create Date: 2026-08-28
"""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "8c2e4f6a9b10"
down_revision: str | Sequence[str] | None = "5f42d0b8a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _step(key: str, role: str, sequence: int, parallel_group: str | None = None) -> dict:
    value = {"key": key, "role": role, "sequence": sequence}
    if parallel_group:
        value["parallel_group"] = parallel_group
    return value


def _templates() -> list[dict]:
    records = [
        {
            "id": "051be2d8-fd95-4bf4-8232-e9eb8b0fc101",
            "workflow_key": "v0_5_fixed_orchestration",
            "version": "1.0.0",
            "name": "V0.5 fixed research and strategy workflow",
            "description": "Records the existing Research + Strategy -> Chief -> Reviewer flow.",
            "definition": {
                "control_plane": "v0.5",
                "selection": "default",
                "steps": [
                    _step("research", "research", 1, "analysis"),
                    _step("strategy", "strategy", 1, "analysis"),
                    _step("chief", "chief_of_staff", 2),
                    _step("review", "reviewer", 3),
                ],
            },
        },
        {
            "id": "3ae2a527-adac-4908-ad14-acac89e71d02",
            "workflow_key": "v0_5_marketing_extension",
            "version": "1.0.0",
            "name": "V0.5 marketing extension workflow",
            "description": "Records the existing opt-in Marketing extension without changing it.",
            "definition": {
                "control_plane": "v0.5",
                "selection": "marketing",
                "steps": [
                    _step("research", "research", 1, "analysis"),
                    _step("strategy", "strategy", 1, "analysis"),
                    _step("marketing", "marketing", 2),
                    _step("chief", "chief_of_staff", 3),
                    _step("review", "reviewer", 4),
                ],
            },
        },
        {
            "id": "8fefc676-29a4-41fd-91cb-693023db5b03",
            "workflow_key": "v0_5_legal_review_extension",
            "version": "1.0.0",
            "name": "V0.5 legal review extension workflow",
            "description": (
                "Records the existing opt-in Legal review extension without changing it."
            ),
            "definition": {
                "control_plane": "v0.5",
                "selection": "legal_review",
                "steps": [
                    _step("research", "research", 1, "analysis"),
                    _step("strategy", "strategy", 1, "analysis"),
                    _step("legal_review", "legal_review", 2),
                    _step("chief", "chief_of_staff", 3),
                    _step("review", "reviewer", 4),
                ],
            },
        },
    ]
    now = datetime.now(UTC)
    for record in records:
        payload = json.dumps(record["definition"], sort_keys=True, separators=(",", ":"))
        record["checksum"] = hashlib.sha256(payload.encode()).hexdigest()
        record["active"] = True
        record["created_at"] = now
        record["updated_at"] = now
    return records


def upgrade() -> None:
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_key", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_key", "version"),
    )
    op.create_index(
        op.f("ix_workflow_definitions_active"),
        "workflow_definitions",
        ["active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_definitions_workflow_key"),
        "workflow_definitions",
        ["workflow_key"],
        unique=False,
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=80), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("task_run_id", sa.String(length=36), nullable=False),
        sa.Column("definition_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_key", sa.String(length=100), nullable=False),
        sa.Column("workflow_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("definition_snapshot", sa.JSON(), nullable=False),
        sa.Column("execution_plan", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["definition_id"], ["workflow_definitions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_run_id"], ["task_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_run_id"),
    )
    op.create_index(
        op.f("ix_workflow_runs_definition_id"), "workflow_runs", ["definition_id"], unique=False
    )
    op.create_index(op.f("ix_workflow_runs_status"), "workflow_runs", ["status"], unique=False)
    op.create_index(op.f("ix_workflow_runs_task_id"), "workflow_runs", ["task_id"], unique=False)
    op.create_index(
        op.f("ix_workflow_runs_task_run_id"), "workflow_runs", ["task_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_workflow_runs_tenant_id"), "workflow_runs", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_workflow_runs_workflow_key"), "workflow_runs", ["workflow_key"], unique=False
    )

    online_migration = not op.get_context().as_sql
    definition_type: sa.types.TypeEngine = sa.JSON() if online_migration else sa.Text()
    workflow_definition_seed = sa.table(
        "workflow_definitions",
        sa.column("id", sa.String()),
        sa.column("workflow_key", sa.String()),
        sa.column("version", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("definition", definition_type),
        sa.column("checksum", sa.String()),
        sa.column("active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    records = _templates()
    if not online_migration:
        records = [
            {
                **record,
                "definition": json.dumps(
                    record["definition"], sort_keys=True, separators=(",", ":")
                ),
            }
            for record in records
        ]
    op.bulk_insert(workflow_definition_seed, records)


def downgrade() -> None:
    op.drop_index(op.f("ix_workflow_runs_workflow_key"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_tenant_id"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_task_run_id"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_task_id"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_status"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_definition_id"), table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index(op.f("ix_workflow_definitions_workflow_key"), table_name="workflow_definitions")
    op.drop_index(op.f("ix_workflow_definitions_active"), table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
