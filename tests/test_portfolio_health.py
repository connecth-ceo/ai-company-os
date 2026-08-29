import asyncio
from datetime import date, timedelta

from app.db import SessionLocal
from app.models import Task, TaskStatus


async def set_task_status(task_id: str, status: TaskStatus) -> None:
    async with SessionLocal() as session:
        task = await session.get(Task, task_id)
        assert task is not None
        task.status = status
        await session.commit()


def create_goal(client, title: str, target_date: date, *, tenant: str = "owner") -> dict:
    response = client.post(
        "/api/v1/goals",
        headers={"X-Tenant-ID": tenant},
        json={"title": title, "target_date": target_date.isoformat()},
    )
    assert response.status_code == 201
    return response.json()


def test_empty_portfolio_health_is_read_only(client):
    before = client.get("/api/v1/audit-events").json()
    response = client.get("/api/v1/portfolio/health")
    after = client.get("/api/v1/audit-events").json()

    assert response.status_code == 200
    body = response.json()
    assert body["rule_version"] == "portfolio-health-v1"
    assert body["goals"] == []
    assert body["projects"] == []
    assert body["summary"] == {
        "open_goals": 0,
        "overdue_goals": 0,
        "due_soon_goals": 0,
        "open_projects": 0,
        "on_hold_projects": 0,
        "projects_with_failed_tasks": 0,
        "total_tasks": 0,
        "completed_tasks": 0,
        "completion_percent": 0,
        "health_counts": {
            "healthy": 0,
            "watch": 0,
            "action": 0,
            "critical": 0,
            "closed": 0,
        },
    }
    assert after == before


def test_portfolio_health_classifies_deadlines_progress_and_failures(client):
    current_date = date.today()
    overdue_goal = create_goal(
        client,
        "기한 초과 목표",
        current_date - timedelta(days=1),
    )
    soon_goal = create_goal(
        client,
        "마감 임박 목표",
        current_date + timedelta(days=7),
    )
    closed_goal = create_goal(
        client,
        "종료 목표",
        current_date + timedelta(days=60),
    )
    assert (
        client.post(
            f"/api/v1/goals/{closed_goal['id']}/transition",
            json={"status": "achieved"},
        ).status_code
        == 200
    )

    project = client.post(
        "/api/v1/projects",
        json={"title": "실패 업무 포함", "goal_id": overdue_goal["id"]},
    ).json()
    held_project = client.post(
        "/api/v1/projects",
        json={"title": "보류 프로젝트", "status": "on_hold"},
    ).json()
    completed_task = client.post(
        "/api/v1/tasks",
        json={"title": "완료 업무", "request": "완료", "project_id": project["id"]},
    ).json()
    failed_task = client.post(
        "/api/v1/tasks",
        json={"title": "실패 업무", "request": "실패", "project_id": project["id"]},
    ).json()
    asyncio.run(set_task_status(completed_task["id"], TaskStatus.COMPLETED))
    asyncio.run(set_task_status(failed_task["id"], TaskStatus.FAILED))

    create_goal(
        client,
        "다른 회사 목표",
        current_date - timedelta(days=30),
        tenant="other",
    )
    client.post(
        "/api/v1/projects",
        headers={"X-Tenant-ID": "other"},
        json={"title": "다른 회사 프로젝트"},
    )

    body = client.get("/api/v1/portfolio/health").json()
    goals = {item["id"]: item for item in body["goals"]}
    projects = {item["id"]: item for item in body["projects"]}

    assert set(goals) == {overdue_goal["id"], soon_goal["id"], closed_goal["id"]}
    assert set(projects) == {project["id"], held_project["id"]}
    assert goals[overdue_goal["id"]]["health_level"] == "critical"
    assert goals[overdue_goal["id"]]["health_reason"] == "target_date_overdue"
    assert goals[overdue_goal["id"]]["days_to_target"] == -1
    assert goals[overdue_goal["id"]]["completion_percent"] == 50
    assert goals[soon_goal["id"]]["health_level"] == "watch"
    assert goals[soon_goal["id"]]["health_reason"] == "target_date_due_soon"
    assert goals[closed_goal["id"]]["health_level"] == "closed"
    assert projects[project["id"]]["health_level"] == "action"
    assert projects[project["id"]]["health_reason"] == "failed_tasks"
    assert projects[project["id"]]["total_tasks"] == 2
    assert projects[project["id"]]["completed_tasks"] == 1
    assert projects[project["id"]]["failed_tasks"] == 1
    assert projects[project["id"]]["completion_percent"] == 50
    assert projects[held_project["id"]]["health_reason"] == "project_on_hold"

    assert body["summary"] == {
        "open_goals": 2,
        "overdue_goals": 1,
        "due_soon_goals": 1,
        "open_projects": 2,
        "on_hold_projects": 1,
        "projects_with_failed_tasks": 1,
        "total_tasks": 2,
        "completed_tasks": 1,
        "completion_percent": 50,
        "health_counts": {
            "healthy": 0,
            "watch": 1,
            "action": 2,
            "critical": 1,
            "closed": 1,
        },
    }

    limited = client.get("/api/v1/portfolio/health?limit=1").json()
    assert len(limited["goals"]) == 1
    assert len(limited["projects"]) == 1
    assert limited["summary"] == body["summary"]

