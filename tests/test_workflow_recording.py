from unittest.mock import AsyncMock, patch

import pytest

from app.db import SessionLocal
from app.models import Task, TaskRun, TaskStatus


def create_and_run(client, request: str, *, tenant: str = "owner") -> dict:
    headers = {"X-Tenant-ID": tenant}
    created = client.post(
        "/api/v1/tasks",
        json={"title": "Workflow recording", "request": request},
        headers=headers,
    )
    assert created.status_code == 201
    dispatched = client.post(f"/api/v1/tasks/{created.json()['id']}/run", headers=headers)
    assert dispatched.status_code == 202
    detail = client.get(f"/api/v1/tasks/{created.json()['id']}", headers=headers)
    assert detail.status_code == 200
    return detail.json()


def test_default_workflow_run_records_immutable_plan_and_result(client):
    detail = create_and_run(client, "시장 진입 전략을 검토해줘.")

    workflow = detail["runs"][0]["workflow_run"]
    assert workflow["status"] == "completed"
    assert workflow["workflow_key"] == "v0_5_fixed_orchestration"
    assert workflow["workflow_version"] == "1.0.0"
    assert workflow["definition_snapshot"]["checksum"]
    assert workflow["execution_plan"]["selected_workflow"] == "default"
    assert [step["key"] for step in workflow["execution_plan"]["steps"]] == [
        "research",
        "strategy",
        "chief",
        "review",
    ]
    assert workflow["result_summary"]["verdict"] == "PASS"
    assert workflow["result_summary"]["completed_steps"] == [
        "research",
        "strategy",
        "chief",
        "review",
    ]

    fetched = client.get(f"/api/v1/workflow-runs/{workflow['id']}")
    hidden = client.get(
        f"/api/v1/workflow-runs/{workflow['id']}",
        headers={"X-Tenant-ID": "other"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["task_id"] == detail["id"]
    assert hidden.status_code == 404


@pytest.mark.parametrize(
    ("task_request", "expected_key", "expected_step"),
    [
        ("/marketing 신제품 캠페인 초안", "v0_5_marketing_extension", "marketing"),
        ("/legal 계약 위험을 검토해줘", "v0_5_legal_review_extension", "legal_review"),
    ],
)
def test_explicit_specialist_selects_versioned_template(
    client, task_request, expected_key, expected_step
):
    detail = create_and_run(client, task_request)

    workflow = detail["runs"][0]["workflow_run"]
    steps = [step["key"] for step in workflow["execution_plan"]["steps"]]
    assert workflow["workflow_key"] == expected_key
    assert expected_step in steps
    assert workflow["result_summary"]["selected_workflow"] in {"marketing", "legal_review"}


def test_workflow_definition_registry_is_read_only_and_versioned(client):
    response = client.get("/api/v1/workflow-definitions")

    assert response.status_code == 200
    definitions = response.json()
    assert len(definitions) == 3
    assert {item["version"] for item in definitions} == {"1.0.0"}
    assert {item["workflow_key"] for item in definitions} == {
        "v0_5_fixed_orchestration",
        "v0_5_marketing_extension",
        "v0_5_legal_review_extension",
    }
    assert all(len(item["checksum"]) == 64 for item in definitions)


def test_failed_task_preserves_failed_workflow_record(client):
    with patch(
        "app.services.task_service.orchestrate",
        new=AsyncMock(side_effect=RuntimeError("recorded failure")),
    ):
        detail = create_and_run(client, "실패 기록을 검증해줘.")

    workflow = detail["runs"][0]["workflow_run"]
    assert detail["status"] == "failed"
    assert workflow["status"] == "failed"
    assert workflow["error"] == "RuntimeError: recorded failure"
    assert workflow["finished_at"] is not None


def test_audit_events_reference_workflow_version(client):
    detail = create_and_run(client, "감사 기록을 검증해줘.")
    workflow = detail["runs"][0]["workflow_run"]
    events = client.get("/api/v1/audit-events").json()

    started = next(event for event in events if event["action"] == "task.started")
    completed = next(event for event in events if event["action"] == "task.completed")
    assert started["details"]["workflow_key"] == workflow["workflow_key"]
    assert started["details"]["workflow_version"] == "1.0.0"
    assert completed["details"]["workflow_run_id"] == workflow["id"]


async def test_legacy_task_run_without_workflow_record_remains_readable(client):
    async with SessionLocal() as session:
        task = Task(
            title="Legacy run",
            request="마이그레이션 이전 실행",
            status=TaskStatus.COMPLETED,
            result="legacy result",
        )
        session.add(task)
        await session.flush()
        session.add(
            TaskRun(
                task_id=task.id,
                status=TaskStatus.COMPLETED,
                attempt=1,
            )
        )
        await session.commit()
        task_id = task.id

    detail = client.get(f"/api/v1/tasks/{task_id}")

    assert detail.status_code == 200
    assert detail.json()["runs"][0]["workflow_run"] is None
