import asyncio
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.db import SessionLocal
from app.models import Approval, Task, TaskRun, TaskStatus


def commitment_payload(statement: str, due_at: datetime) -> dict[str, str]:
    return {
        "statement": statement,
        "owner_id": "CEO",
        "due_at": due_at.isoformat(),
    }


async def configure_task_state(
    task_id: str,
    *,
    status: TaskStatus,
    age: timedelta,
    failures: int = 0,
) -> None:
    current = datetime.now(UTC)
    async with SessionLocal() as session:
        task = await session.get(Task, task_id)
        assert task is not None
        task.status = status
        task.updated_at = current - age
        if failures:
            session.add_all(
                TaskRun(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    attempt=index + 1,
                    started_at=current - age,
                    finished_at=current - age + timedelta(seconds=index),
                )
                for index in range(failures)
            )
        await session.commit()


async def age_approval(approval_id: str, *, age: timedelta) -> None:
    async with SessionLocal() as session:
        approval = await session.get(Approval, approval_id)
        assert approval is not None
        approval.created_at = datetime.now(UTC) - age
        await session.commit()


def test_attention_queue_is_empty_without_signals(client):
    response = client.get("/api/v1/attention")

    assert response.status_code == 200
    body = response.json()
    assert body["rule_version"] == "attention-rules-v1"
    assert body["total"] == 0
    assert body["items"] == []
    assert body["counts"] == {
        "info": 0,
        "watch": 0,
        "action": 0,
        "decision": 0,
        "critical": 0,
    }


def test_overdue_commitments_receive_escalating_levels_and_are_tenant_safe(client):
    now = datetime.now(UTC)
    action = client.post(
        "/api/v1/commitments",
        json=commitment_payload("Action", now - timedelta(hours=2)),
    ).json()
    decision = client.post(
        "/api/v1/commitments",
        json=commitment_payload("Decision", now - timedelta(hours=30)),
    ).json()
    critical = client.post(
        "/api/v1/commitments",
        json=commitment_payload("Critical", now - timedelta(hours=80)),
    ).json()
    closed = client.post(
        "/api/v1/commitments",
        json=commitment_payload("Closed", now - timedelta(hours=80)),
    ).json()
    client.post(
        f"/api/v1/commitments/{closed['id']}/transition",
        json={"status": "completed"},
    )
    client.post(
        "/api/v1/commitments",
        headers={"X-Tenant-ID": "other"},
        json=commitment_payload("Other tenant", now - timedelta(hours=80)),
    )

    items = client.get("/api/v1/attention").json()["items"]

    assert [item["resource_id"] for item in items] == [
        critical["id"],
        decision["id"],
        action["id"],
    ]
    assert [item["level"] for item in items] == ["critical", "decision", "action"]
    assert all(item["kind"] == "overdue_commitment" for item in items)


def test_long_running_and_failed_tasks_are_classified_without_execution(client):
    task_ids = []
    for title in ("Fresh", "Stale", "Very stale", "One fail", "Two fails", "Three fails"):
        task_ids.append(
            client.post(
                "/api/v1/tasks",
                json={"title": title, "request": "test"},
            ).json()["id"]
        )
    asyncio.run(
        configure_task_state(
            task_ids[0], status=TaskStatus.RUNNING, age=timedelta(minutes=5)
        )
    )
    asyncio.run(
        configure_task_state(
            task_ids[1], status=TaskStatus.RUNNING, age=timedelta(minutes=30)
        )
    )
    asyncio.run(
        configure_task_state(
            task_ids[2], status=TaskStatus.RUNNING, age=timedelta(minutes=60)
        )
    )
    for index, failures in enumerate((1, 2, 3), start=3):
        asyncio.run(
            configure_task_state(
                task_ids[index],
                status=TaskStatus.FAILED,
                age=timedelta(minutes=failures),
                failures=failures,
            )
        )

    items = client.get("/api/v1/attention").json()["items"]
    by_resource = {item["resource_id"]: item for item in items}

    assert task_ids[0] not in by_resource
    assert by_resource[task_ids[1]]["level"] == "action"
    assert by_resource[task_ids[2]]["level"] == "critical"
    assert by_resource[task_ids[3]]["level"] == "watch"
    assert by_resource[task_ids[4]]["level"] == "decision"
    assert by_resource[task_ids[5]]["level"] == "critical"
    assert by_resource[task_ids[5]]["evidence"]["failure_count"] == 3


def test_pending_approvals_are_decisions_and_escalate_by_risk_or_age(client):
    normal = client.post(
        "/api/v1/approvals",
        json={"action": "게시 승인", "reason": "외부 공개", "risk": "medium"},
    ).json()
    high_age = client.post(
        "/api/v1/approvals",
        json={"action": "오래된 승인", "reason": "대기 중", "risk": "low"},
    ).json()
    critical_risk = client.post(
        "/api/v1/approvals",
        json={"action": "긴급 승인", "reason": "고위험", "risk": "critical"},
    ).json()
    asyncio.run(age_approval(high_age["id"], age=timedelta(hours=80)))

    items = client.get("/api/v1/attention?kind=pending_approval").json()["items"]
    levels = {item["resource_id"]: item["level"] for item in items}

    assert levels[normal["id"]] == "decision"
    assert levels[high_age["id"]] == "critical"
    assert levels[critical_risk["id"]] == "critical"


def test_attention_filters_and_limit_are_applied_after_priority_sort(client):
    now = datetime.now(UTC)
    for index, hours in enumerate((2, 30, 80)):
        client.post(
            "/api/v1/commitments",
            json=commitment_payload(f"Item {index}", now - timedelta(hours=hours)),
        )

    response = client.get(
        "/api/v1/attention?min_level=decision&kind=overdue_commitment&limit=1"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["counts"]["critical"] == 1
    assert body["counts"]["decision"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["level"] == "critical"


def test_daily_briefing_includes_top_attention_without_ai_call(client):
    now = datetime(2026, 8, 28, 0, 0, tzinfo=UTC)

    async def build() -> str:
        async with SessionLocal() as session:
            session.add(
                Approval(
                    tenant_id="owner",
                    action="중요 계약 승인",
                    reason="대표 결정 필요",
                    risk="critical",
                    created_at=now - timedelta(hours=1),
                )
            )
            await session.commit()
            from app.services.daily_briefing import build_daily_briefing

            return await build_daily_briefing(
                session,
                "owner",
                now=now,
                settings=Settings(ai_provider="mock"),
            )

    briefing = asyncio.run(build())

    assert "대표 확인 필요 1건" in briefing
    assert "대표 주의 큐" in briefing
    assert "[긴급] 대표 승인 대기: 중요 계약 승인" in briefing
    assert "승인 또는 거절 결정을 내려 주세요." in briefing
