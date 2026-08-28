import asyncio
from datetime import UTC, datetime, timedelta

from app.db import SessionLocal
from app.models import Delegation, Task, TaskRun, TaskStatus


def _create_delegation(client):
    parent = client.post(
        "/api/v1/tasks",
        json={"title": "Recovery parent", "request": "복구 검증"},
    ).json()
    response = client.post(
        f"/api/v1/tasks/{parent['id']}/delegations",
        json={
            "title": "Recovery child",
            "request": "비용 없는 복구 상태 검증",
            "delegated_role": "research",
            "reason": "worker recovery test",
            "token_budget": 2_000,
            "timeout_seconds": 60,
            "cost_budget_usd": 0.5,
        },
    )
    assert response.status_code == 201
    return response.json()


async def _make_stale_dispatched(delegation_id: str) -> None:
    async with SessionLocal() as session:
        delegation = await session.get(Delegation, delegation_id)
        child = await session.get(Task, delegation.child_task_id)
        delegation.status = "dispatched"
        delegation.updated_at = datetime.now(UTC) - timedelta(minutes=10)
        child.status = TaskStatus.DISPATCHED
        await session.commit()


async def _make_stale_running(delegation_id: str) -> str:
    async with SessionLocal() as session:
        delegation = await session.get(Delegation, delegation_id)
        child = await session.get(Task, delegation.child_task_id)
        started_at = datetime.now(UTC) - timedelta(minutes=10)
        task_run = TaskRun(
            task_id=child.id,
            status=TaskStatus.RUNNING,
            agent="Research Agent",
            started_at=started_at,
        )
        session.add(task_run)
        await session.flush()
        delegation.status = "running"
        delegation.task_run_id = task_run.id
        delegation.started_at = started_at
        delegation.updated_at = started_at
        child.status = TaskStatus.RUNNING
        await session.commit()
        return task_run.id


def test_stale_dispatch_dry_run_then_safe_retry_reset_is_idempotent(client):
    delegation = _create_delegation(client)
    asyncio.run(_make_stale_dispatched(delegation["id"]))

    preview = client.post("/api/v1/delegations/recover-stale", json={}).json()
    assert preview == {
        "dry_run": True,
        "scanned": 1,
        "stale": 1,
        "reset_for_retry": 1,
        "quarantined": 0,
        "items": [
            {
                "delegation_id": delegation["id"],
                "child_task_id": delegation["child_task_id"],
                "previous_status": "dispatched",
                "action": "reset_for_retry",
            }
        ],
    }
    assert client.get(f"/api/v1/delegations/{delegation['id']}").json()["status"] == ("dispatched")

    recovered = client.post(
        "/api/v1/delegations/recover-stale",
        json={"dry_run": False},
    ).json()
    assert recovered["reset_for_retry"] == 1
    detail = client.get(f"/api/v1/delegations/{delegation['id']}").json()
    child = client.get(f"/api/v1/tasks/{delegation['child_task_id']}").json()
    assert detail["status"] == "created"
    assert detail["task_run_id"] is None
    assert child["status"] == "queued"

    repeated = client.post(
        "/api/v1/delegations/recover-stale",
        json={"dry_run": False},
    ).json()
    assert repeated["stale"] == 0
    actions = {event["action"] for event in client.get("/api/v1/audit-events").json()}
    assert "delegation.recovered_before_start" in actions


def test_stale_running_execution_is_quarantined_without_automatic_retry(client):
    delegation = _create_delegation(client)
    task_run_id = asyncio.run(_make_stale_running(delegation["id"]))

    result = client.post(
        "/api/v1/delegations/recover-stale",
        json={"dry_run": False},
    ).json()

    assert result["quarantined"] == 1
    detail = client.get(f"/api/v1/delegations/{delegation['id']}").json()
    child = client.get(f"/api/v1/tasks/{delegation['child_task_id']}").json()
    run = next(item for item in child["runs"] if item["id"] == task_run_id)
    assert detail["status"] == "failed"
    assert "automatic retry is disabled" in detail["error"]
    assert child["status"] == "failed"
    assert run["status"] == "failed"
    assert run["finished_at"]

    redispatch = client.post(f"/api/v1/delegations/{delegation['id']}/run")
    assert redispatch.status_code == 409
    assert "newly created" in redispatch.json()["detail"]
    actions = {event["action"] for event in client.get("/api/v1/audit-events").json()}
    assert "delegation.stale_execution_quarantined" in actions


def test_recovery_scan_is_tenant_isolated(client):
    delegation = _create_delegation(client)
    asyncio.run(_make_stale_dispatched(delegation["id"]))

    hidden = client.post(
        "/api/v1/delegations/recover-stale",
        headers={"X-Tenant-ID": "other"},
        json={"dry_run": False},
    ).json()
    assert hidden["scanned"] == 0
    assert client.get(f"/api/v1/delegations/{delegation['id']}").json()["status"] == ("dispatched")
