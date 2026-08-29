import pytest

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import Task
from app.schemas import DelegatedTaskCreate
from app.services.delegation import DelegationRejected, create_delegation


def create_task(client, *, tenant="owner", project_id=None, title="Parent"):
    payload = {"title": title, "request": f"{title} 업무"}
    if project_id:
        payload["project_id"] = project_id
    response = client.post("/api/v1/tasks", json=payload, headers={"X-Tenant-ID": tenant})
    assert response.status_code == 201
    return response.json()


def delegate(client, parent_id, *, role="research", title="Child", **overrides):
    payload = {
        "title": title,
        "request": f"{title} 세부 업무",
        "delegated_role": role,
        "reason": "전문 역할에 제한적으로 위임",
    }
    payload.update(overrides)
    return client.post(f"/api/v1/tasks/{parent_id}/delegations", json=payload)


def test_mediated_delegation_inherits_boundaries_and_stays_queued(client):
    project = client.post("/api/v1/projects", json={"title": "Delegation project"}).json()
    parent = create_task(client, project_id=project["id"])

    response = delegate(client, parent["id"], role="research")

    assert response.status_code == 201
    record = response.json()
    assert record["tenant_id"] == "owner"
    assert record["project_id"] == project["id"]
    assert record["parent_task_id"] == parent["id"]
    assert record["depth"] == 1
    assert record["status"] == "created"
    assert record["approval_id"] is None
    assert record["policy_snapshot"]["approval_gate"]["required"] is False
    assert record["policy_snapshot"]["allowed_tools"] == ["web_search"]
    assert record["policy_snapshot"]["approval_policy"] == "none"

    child = client.get(f"/api/v1/tasks/{record['child_task_id']}").json()
    assert child["parent_task_id"] == parent["id"]
    assert child["project_id"] == project["id"]
    assert child["source"] == "delegation"
    assert child["status"] == "queued"
    assert client.get(f"/api/v1/tasks/{parent['id']}/delegations").json()[0]["id"] == record["id"]

    events = client.get("/api/v1/audit-events").json()
    delegated = next(event for event in events if event["action"] == "task.delegated")
    assert delegated["details"]["initiator"] == "CEO"
    assert delegated["details"]["reason"] == "전문 역할에 제한적으로 위임"
    assert delegated["details"]["approval_id"] is None


def test_delegation_enforces_depth_and_child_limits(client):
    root = create_task(client)
    parent_id = root["id"]
    for depth in range(1, 4):
        response = delegate(client, parent_id, title=f"Depth {depth}")
        assert response.status_code == 201
        assert response.json()["depth"] == depth
        parent_id = response.json()["child_task_id"]

    too_deep = delegate(client, parent_id, title="Depth 4")
    assert too_deep.status_code == 409
    assert "maximum delegation depth" in too_deep.json()["detail"]

    second_root = create_task(client, title="Child limit root")
    for number in range(5):
        assert delegate(client, second_root["id"], title=f"Child {number}").status_code == 201
    too_many = delegate(client, second_root["id"], title="Child 6")
    assert too_many.status_code == 409
    assert "maximum number of child tasks" in too_many.json()["detail"]


def test_delegation_rejects_unknown_role_budget_and_pending_approval(client):
    unknown_parent = create_task(client, title="Unknown role")
    unknown = delegate(client, unknown_parent["id"], role="unregistered_agent")
    assert unknown.status_code == 409
    assert "operational agent registry" in unknown.json()["detail"]

    budget_parent = create_task(client, title="Budget")
    over_budget = delegate(client, budget_parent["id"], token_budget=50_001)
    assert over_budget.status_code == 409
    assert "token_budget" in over_budget.json()["detail"]

    approval_parent = create_task(client, title="Approval")
    approval = client.post(
        "/api/v1/approvals",
        json={
            "action": "외부 전송",
            "reason": "대표 승인 필요",
            "task_id": approval_parent["id"],
        },
    )
    assert approval.status_code == 201
    blocked = delegate(client, approval_parent["id"])
    assert blocked.status_code == 409
    assert "awaits approval" in blocked.json()["detail"]

    rejected_events = [
        event
        for event in client.get("/api/v1/audit-events").json()
        if event["action"] == "task.delegation_rejected"
    ]
    assert {event["details"]["code"] for event in rejected_events} >= {
        "role_not_allowed",
        "budget_limit",
        "approval_pending",
    }


def test_delegation_is_tenant_isolated(client):
    parent = create_task(client)
    response = client.post(
        f"/api/v1/tasks/{parent['id']}/delegations",
        headers={"X-Tenant-ID": "other"},
        json={
            "title": "Cross tenant",
            "request": "다른 회사 업무",
            "delegated_role": "research",
            "reason": "허용되면 안 됨",
        },
    )
    assert response.status_code == 404
    assert (
        client.get(
            f"/api/v1/tasks/{parent['id']}/delegations",
            headers={"X-Tenant-ID": "other"},
        ).status_code
        == 404
    )


def test_delegation_rejects_a_completed_project(client):
    project = client.post("/api/v1/projects", json={"title": "Closed project"}).json()
    parent = create_task(client, project_id=project["id"], title="Completed parent")
    assert client.post(f"/api/v1/tasks/{parent['id']}/run").status_code == 202
    assert (
        client.post(
            f"/api/v1/projects/{project['id']}/transition",
            json={"status": "completed"},
        ).status_code
        == 200
    )

    blocked = delegate(client, parent["id"])

    assert blocked.status_code == 409
    assert "completed or archived project" in blocked.json()["detail"]


@pytest.mark.asyncio
async def test_existing_cycle_is_detected_before_creating_child():
    async with SessionLocal() as session:
        first = Task(tenant_id="owner", title="First", request="first")
        second = Task(tenant_id="owner", title="Second", request="second")
        session.add_all((first, second))
        await session.flush()
        first.parent_task_id = second.id
        second.parent_task_id = first.id
        await session.commit()

        payload = DelegatedTaskCreate(
            title="Blocked",
            request="cycle 아래 생성 금지",
            delegated_role="research",
            reason="cycle test",
        )
        with pytest.raises(DelegationRejected, match="cycle") as caught:
            await create_delegation(
                session,
                parent=first,
                payload=payload,
                settings=get_settings(),
                initiator="test",
            )
        assert caught.value.code == "cycle_detected"
