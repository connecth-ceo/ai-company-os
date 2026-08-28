from unittest.mock import patch

from app.agents.contracts import AgentRunResult, RuntimeUsage
from app.core.config import Settings, get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Delegation
from app.services.delegation_execution import dispatch_delegation, execute_delegation


def _create_delegation(client, *, role="research", cost_budget_usd=0.5):
    parent = client.post(
        "/api/v1/tasks",
        json={"title": "Parent", "request": "대표 업무"},
    ).json()
    response = client.post(
        f"/api/v1/tasks/{parent['id']}/delegations",
        json={
            "title": "Delegated child",
            "request": "시장 신호를 제한적으로 분석해줘",
            "delegated_role": role,
            "reason": "역할 기반 검증",
            "token_budget": 2_000,
            "timeout_seconds": 60,
            "cost_budget_usd": cost_budget_usd,
        },
    )
    assert response.status_code == 201
    return parent, response.json()


def test_delegated_task_requires_mediated_execution_endpoint(client):
    _, delegation = _create_delegation(client)

    blocked = client.post(f"/api/v1/tasks/{delegation['child_task_id']}/run")

    assert blocked.status_code == 409
    assert "delegation execution endpoint" in blocked.json()["detail"]


def test_mock_delegated_role_execution_records_ledger_without_workflow(client):
    _, delegation = _create_delegation(client)

    dispatched = client.post(f"/api/v1/delegations/{delegation['id']}/run")

    assert dispatched.status_code == 202
    detail = client.get(f"/api/v1/delegations/{delegation['id']}").json()
    child = client.get(f"/api/v1/tasks/{delegation['child_task_id']}").json()
    assert detail["status"] == "completed"
    assert detail["runtime_name"] == "mock_delegated"
    assert detail["task_run_id"]
    assert detail["total_tokens"] == 0
    assert detail["finished_at"]
    assert child["status"] == "completed"
    assert child["result"].startswith("[Mock Research Agent]")
    assert child["runs"][0]["agent"] == "Research Agent"
    assert child["runs"][0]["workflow_run"] is None
    assert child["runs"][0]["artifacts"]["delegation_id"] == delegation["id"]

    events = client.get("/api/v1/audit-events").json()
    actions = {event["action"] for event in events}
    assert "delegation.execution_dispatched" in actions
    assert "delegation.execution_started" in actions
    assert "delegation.execution_completed" in actions


def test_delegation_execution_is_single_dispatch_and_tenant_isolated(client):
    _, delegation = _create_delegation(client)

    hidden = client.get(f"/api/v1/delegations/{delegation['id']}", headers={"X-Tenant-ID": "other"})
    first = client.post(f"/api/v1/delegations/{delegation['id']}/run")
    second = client.post(f"/api/v1/delegations/{delegation['id']}/run")

    assert hidden.status_code == 404
    assert first.status_code == 202
    assert second.status_code == 409
    child = client.get(f"/api/v1/tasks/{delegation['child_task_id']}").json()
    assert len(child["runs"]) == 1


def test_sensitive_delegation_requires_explicit_ceo_approval_before_dispatch(client):
    _, delegation = _create_delegation(client, role="legal_review")

    assert delegation["approval_id"]
    assert delegation["policy_snapshot"]["approval_gate"] == {
        "required": True,
        "reasons": ["sensitive_role"],
        "cost_threshold_usd": 1.0,
    }
    approval = next(
        item
        for item in client.get("/api/v1/approvals").json()
        if item["id"] == delegation["approval_id"]
    )
    assert approval["status"] == "pending"
    assert approval["task_id"] == delegation["child_task_id"]

    blocked = client.post(f"/api/v1/delegations/{delegation['id']}/run")
    assert blocked.status_code == 409
    assert "explicit CEO approval" in blocked.json()["detail"]

    decided = client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"approved": True, "decided_by": "CEO", "note": "검증 승인"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"

    dispatched = client.post(f"/api/v1/delegations/{delegation['id']}/run")
    assert dispatched.status_code == 202
    detail = client.get(f"/api/v1/delegations/{delegation['id']}").json()
    assert detail["status"] == "completed"
    assert detail["task_run_id"]

    actions = {event["action"] for event in client.get("/api/v1/audit-events").json()}
    assert "approval.requested" in actions
    assert "delegation.approval_approved" in actions


def test_rejected_or_high_cost_delegation_fails_closed(client):
    _, delegation = _create_delegation(client, cost_budget_usd=1.5)
    assert delegation["policy_snapshot"]["approval_gate"]["reasons"] == ["cost_budget"]

    decision = client.post(
        f"/api/v1/approvals/{delegation['approval_id']}/decide",
        json={"approved": False, "decided_by": "CEO"},
    )
    assert decision.status_code == 200
    blocked = client.post(f"/api/v1/delegations/{delegation['id']}/run")
    assert blocked.status_code == 409
    assert "rejected" in blocked.json()["detail"]
    detail = client.get(f"/api/v1/delegations/{delegation['id']}").json()
    assert detail["status"] == "created"
    assert detail["task_run_id"] is None


def test_policy_drift_fails_closed_before_runtime(client):
    _, record = _create_delegation(client)

    async def change_snapshot() -> None:
        async with SessionLocal() as session:
            delegation = await session.get(Delegation, record["id"])
            snapshot = dict(delegation.policy_snapshot)
            snapshot["allowed_tools"] = []
            delegation.policy_snapshot = snapshot
            await session.commit()

    import asyncio

    asyncio.run(change_snapshot())
    response = client.post(f"/api/v1/delegations/{record['id']}/run")

    assert response.status_code == 409
    assert "policy differs" in response.json()["detail"]
    detail = client.get(f"/api/v1/delegations/{record['id']}").json()
    assert detail["status"] == "created"
    assert detail["task_run_id"] is None


def test_worker_queue_failure_restores_retryable_delegation_state(client):
    worker_settings = Settings(ai_provider="mock", task_execution_mode="worker")
    app.dependency_overrides[get_settings] = lambda: worker_settings
    try:
        _, delegation = _create_delegation(client)
        with patch("app.worker.execute_delegation_job.delay", side_effect=ConnectionError):
            response = client.post(f"/api/v1/delegations/{delegation['id']}/run")
        detail = client.get(f"/api/v1/delegations/{delegation['id']}").json()
        child = client.get(f"/api/v1/tasks/{delegation['child_task_id']}").json()
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 503
    assert detail["status"] == "created"
    assert child["status"] == "queued"
    assert "Queue dispatch failed" in detail["error"]


def test_runtime_token_overrun_fails_task_and_records_no_result(client):
    _, record = _create_delegation(client)

    class OverBudgetRuntime:
        name = "over_budget_test"

        async def run(self, definition, input_text, *, max_output_tokens=None):
            del definition, input_text, max_output_tokens
            return AgentRunResult(
                final_output="must not be exposed",
                usage=RuntimeUsage(input_tokens=1_500, output_tokens=600, total_tokens=2_100),
            )

    async def execute() -> None:
        settings = Settings(ai_provider="mock")
        async with SessionLocal() as session:
            delegation = await session.get(Delegation, record["id"])
            await dispatch_delegation(session, delegation, settings, actor="test")
        async with SessionLocal() as session:
            await execute_delegation(
                session,
                record["id"],
                runtime=OverBudgetRuntime(),
            )

    import asyncio

    asyncio.run(execute())
    detail = client.get(f"/api/v1/delegations/{record['id']}").json()
    child = client.get(f"/api/v1/tasks/{record['child_task_id']}").json()
    assert detail["status"] == "failed"
    assert "exceeded" in detail["error"]
    assert child["status"] == "failed"
    assert child["result"] is None
    assert child["runs"][0]["status"] == "failed"
