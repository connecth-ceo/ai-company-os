import hashlib
import json
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WorkflowDefinition

WORKFLOW_VERSION = "1.0.0"
DEFAULT_TEMPLATE_KEY = "v0_5_fixed_orchestration"
MARKETING_TEMPLATE_KEY = "v0_5_marketing_extension"
LEGAL_TEMPLATE_KEY = "v0_5_legal_review_extension"


def _step(key: str, role: str, sequence: int, *, parallel_group: str | None = None) -> dict:
    value = {"key": key, "role": role, "sequence": sequence}
    if parallel_group:
        value["parallel_group"] = parallel_group
    return value


WORKFLOW_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "workflow_key": DEFAULT_TEMPLATE_KEY,
        "version": WORKFLOW_VERSION,
        "name": "V0.5 fixed research and strategy workflow",
        "description": "Records the existing Research + Strategy -> Chief -> Reviewer flow.",
        "definition": {
            "control_plane": "v0.5",
            "selection": "default",
            "steps": [
                _step("research", "research", 1, parallel_group="analysis"),
                _step("strategy", "strategy", 1, parallel_group="analysis"),
                _step("chief", "chief_of_staff", 2),
                _step("review", "reviewer", 3),
            ],
        },
    },
    {
        "workflow_key": MARKETING_TEMPLATE_KEY,
        "version": WORKFLOW_VERSION,
        "name": "V0.5 marketing extension workflow",
        "description": "Records the existing opt-in Marketing extension without changing it.",
        "definition": {
            "control_plane": "v0.5",
            "selection": "marketing",
            "steps": [
                _step("research", "research", 1, parallel_group="analysis"),
                _step("strategy", "strategy", 1, parallel_group="analysis"),
                _step("marketing", "marketing", 2),
                _step("chief", "chief_of_staff", 3),
                _step("review", "reviewer", 4),
            ],
        },
    },
    {
        "workflow_key": LEGAL_TEMPLATE_KEY,
        "version": WORKFLOW_VERSION,
        "name": "V0.5 legal review extension workflow",
        "description": "Records the existing opt-in Legal review extension without changing it.",
        "definition": {
            "control_plane": "v0.5",
            "selection": "legal_review",
            "steps": [
                _step("research", "research", 1, parallel_group="analysis"),
                _step("strategy", "strategy", 1, parallel_group="analysis"),
                _step("legal_review", "legal_review", 2),
                _step("chief", "chief_of_staff", 3),
                _step("review", "reviewer", 4),
            ],
        },
    },
)


def _checksum(definition: dict[str, Any]) -> str:
    payload = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def catalog_records() -> tuple[dict[str, Any], ...]:
    records = []
    for template in WORKFLOW_TEMPLATES:
        record = deepcopy(template)
        record["checksum"] = _checksum(record["definition"])
        records.append(record)
    return tuple(records)


def get_workflow_template(selected_workflow: str) -> dict[str, Any]:
    key = {
        "marketing": MARKETING_TEMPLATE_KEY,
        "legal_review": LEGAL_TEMPLATE_KEY,
    }.get(selected_workflow, DEFAULT_TEMPLATE_KEY)
    return deepcopy(next(item for item in catalog_records() if item["workflow_key"] == key))


def build_execution_plan(
    selected_workflow: str,
    *,
    max_reworks: int,
    provider: str,
    model: str,
) -> dict[str, Any]:
    template = get_workflow_template(selected_workflow)
    return {
        "workflow_key": template["workflow_key"],
        "workflow_version": template["version"],
        "selected_workflow": selected_workflow,
        "steps": deepcopy(template["definition"]["steps"]),
        "review_policy": {"max_reworks": max_reworks},
        "runtime_policy": {"provider": provider, "model": model},
    }


async def ensure_workflow_definitions(
    session: AsyncSession,
) -> dict[str, WorkflowDefinition]:
    records = catalog_records()
    keys = [record["workflow_key"] for record in records]
    existing = list(
        await session.scalars(
            select(WorkflowDefinition).where(
                WorkflowDefinition.workflow_key.in_(keys),
                WorkflowDefinition.version == WORKFLOW_VERSION,
            )
        )
    )
    by_key = {item.workflow_key: item for item in existing}
    for record in records:
        if record["workflow_key"] in by_key:
            continue
        definition = WorkflowDefinition(active=True, **record)
        session.add(definition)
        by_key[definition.workflow_key] = definition
    await session.flush()
    return by_key
