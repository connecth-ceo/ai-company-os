def create_goal(client, *, tenant="owner", title="유료 고객 20곳 확보"):
    response = client.post(
        "/api/v1/goals",
        json={
            "title": title,
            "description": "회사의 다음 성장 단계",
            "success_metric": "유료 고객 20곳",
            "owner": "CEO",
            "target_date": "2026-12-31",
        },
        headers={"X-Tenant-ID": tenant},
    )
    assert response.status_code == 201
    return response.json()


def test_goal_crud_is_tenant_isolated_and_audited(client):
    goal = create_goal(client)

    detail = client.get(f"/api/v1/goals/{goal['id']}")
    hidden = client.get(
        f"/api/v1/goals/{goal['id']}",
        headers={"X-Tenant-ID": "other"},
    )

    assert detail.status_code == 200
    assert detail.json()["status"] == "active"
    assert detail.json()["target_date"] == "2026-12-31"
    assert hidden.status_code == 404
    assert client.get("/api/v1/goals").json()[0]["id"] == goal["id"]
    assert client.get("/api/v1/goals", headers={"X-Tenant-ID": "other"}).json() == []

    events = client.get("/api/v1/audit-events").json()
    assert any(
        event["action"] == "goal.created" and event["resource_id"] == goal["id"] for event in events
    )


def test_project_can_link_to_goal_and_filter_by_goal(client):
    goal = create_goal(client)
    linked = client.post(
        "/api/v1/projects",
        json={"title": "영업 파이프라인", "goal_id": goal["id"]},
    )
    unlinked = client.post("/api/v1/projects", json={"title": "내부 정비"})

    assert linked.status_code == 201
    assert linked.json()["goal_id"] == goal["id"]
    assert unlinked.status_code == 201
    assert unlinked.json()["goal_id"] is None

    filtered = client.get(f"/api/v1/projects?goal_id={goal['id']}")
    assert filtered.status_code == 200
    assert [project["id"] for project in filtered.json()] == [linked.json()["id"]]


def test_project_rejects_missing_and_cross_tenant_goal(client):
    other_goal = create_goal(client, tenant="other", title="다른 회사 목표")

    missing = client.post(
        "/api/v1/projects",
        json={"title": "없는 목표", "goal_id": "missing"},
    )
    cross_tenant = client.post(
        "/api/v1/projects",
        json={"title": "다른 회사 목표 연결", "goal_id": other_goal["id"]},
    )
    filtered_cross_tenant = client.get(f"/api/v1/projects?goal_id={other_goal['id']}")

    assert missing.status_code == 404
    assert cross_tenant.status_code == 404
    assert filtered_cross_tenant.status_code == 404


def test_goal_status_filter_and_validation(client):
    create_goal(client, title="활성 목표")
    planned = client.post(
        "/api/v1/goals",
        json={"title": "계획 목표", "status": "planned"},
    )
    invalid = client.post(
        "/api/v1/goals",
        json={"title": "잘못된 목표", "status": "unknown"},
    )

    assert planned.status_code == 201
    assert invalid.status_code == 422
    assert [goal["id"] for goal in client.get("/api/v1/goals?status=planned").json()] == [
        planned.json()["id"]
    ]


def test_existing_project_payload_remains_backward_compatible(client):
    response = client.post(
        "/api/v1/projects",
        json={"title": "기존 프로젝트", "description": "기존 형식"},
    )

    assert response.status_code == 201
    assert response.json()["goal_id"] is None


def test_goal_lifecycle_is_tenant_safe_audited_and_terminal(client):
    goal = client.post(
        "/api/v1/goals",
        json={"title": "신규 시장 진출", "status": "planned"},
    ).json()

    assert (
        client.post(
            f"/api/v1/goals/{goal['id']}/transition",
            json={"status": "active", "note": "대표 승인으로 시작"},
        ).json()["status"]
        == "active"
    )
    assert (
        client.post(
            f"/api/v1/goals/{goal['id']}/transition",
            json={"status": "on_hold"},
        ).json()["status"]
        == "on_hold"
    )
    assert (
        client.post(
            f"/api/v1/goals/{goal['id']}/transition",
            json={"status": "active"},
        ).json()["status"]
        == "active"
    )
    assert (
        client.post(
            f"/api/v1/goals/{goal['id']}/transition",
            json={"status": "achieved"},
        ).json()["status"]
        == "achieved"
    )
    assert (
        client.post(
            f"/api/v1/goals/{goal['id']}/transition",
            json={"status": "archived"},
        ).json()["status"]
        == "archived"
    )

    terminal = client.post(
        f"/api/v1/goals/{goal['id']}/transition",
        json={"status": "active"},
    )
    hidden = client.post(
        f"/api/v1/goals/{goal['id']}/transition",
        json={"status": "active"},
        headers={"X-Tenant-ID": "other"},
    )
    assert terminal.status_code == 409
    assert terminal.json()["detail"]["code"] == "invalid_goal_status_transition"
    assert hidden.status_code == 404

    events = client.get("/api/v1/audit-events?limit=100").json()
    active_event = next(
        event
        for event in events
        if event["action"] == "goal.active" and event["resource_id"] == goal["id"]
    )
    assert active_event["details"]["previous_status"] in {"planned", "on_hold"}


def test_terminal_portfolio_statuses_cannot_be_used_at_creation(client):
    achieved_goal = client.post(
        "/api/v1/goals",
        json={"title": "완료된 채로 생성", "status": "achieved"},
    )
    completed_project = client.post(
        "/api/v1/projects",
        json={"title": "완료된 채로 생성", "status": "completed"},
    )

    assert achieved_goal.status_code == 422
    assert completed_project.status_code == 422


def test_project_completion_blocks_unfinished_tasks_and_records_lifecycle(client):
    project = client.post(
        "/api/v1/projects",
        json={"title": "고객 검증", "status": "active"},
    ).json()
    direct_archive = client.post(
        f"/api/v1/projects/{project['id']}/transition",
        json={"status": "archived"},
    )
    assert direct_archive.status_code == 409
    assert direct_archive.json()["detail"]["code"] == "invalid_project_status_transition"
    client.post(
        "/api/v1/tasks",
        json={
            "title": "인터뷰 대상 선정",
            "request": "대상 목록만 기록",
            "project_id": project["id"],
        },
    )

    blocked = client.post(
        f"/api/v1/projects/{project['id']}/transition",
        json={"status": "completed"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "project_has_unfinished_tasks"
    assert client.get(f"/api/v1/projects/{project['id']}").json()["status"] == "active"

    empty_project = client.post(
        "/api/v1/projects",
        json={"title": "완료 가능한 프로젝트", "status": "planned"},
    ).json()
    assert (
        client.post(
            f"/api/v1/projects/{empty_project['id']}/transition",
            json={"status": "active"},
        ).json()["status"]
        == "active"
    )
    assert (
        client.post(
            f"/api/v1/projects/{empty_project['id']}/transition",
            json={"status": "completed", "note": "범위 완료"},
        ).json()["status"]
        == "completed"
    )
    assert (
        client.post(
            f"/api/v1/projects/{empty_project['id']}/transition",
            json={"status": "archived"},
        ).json()["status"]
        == "archived"
    )

    events = client.get("/api/v1/audit-events?limit=100").json()
    completed = next(
        event
        for event in events
        if event["action"] == "project.completed" and event["resource_id"] == empty_project["id"]
    )
    assert completed["details"] == {"previous_status": "active", "note": "범위 완료"}


def test_terminal_goal_and_project_reject_new_children(client):
    goal = create_goal(client)
    project = client.post(
        "/api/v1/projects",
        json={"title": "완료 대상", "goal_id": goal["id"]},
    ).json()
    assert (
        client.post(
            f"/api/v1/projects/{project['id']}/transition",
            json={"status": "completed"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/goals/{goal['id']}/transition",
            json={"status": "achieved"},
        ).status_code
        == 200
    )

    new_project = client.post(
        "/api/v1/projects",
        json={"title": "늦은 프로젝트", "goal_id": goal["id"]},
    )
    new_task = client.post(
        "/api/v1/tasks",
        json={"title": "늦은 업무", "request": "생성되면 안 됨", "project_id": project["id"]},
    )

    assert new_project.status_code == 409
    assert new_project.json()["detail"]["code"] == "goal_not_open_for_projects"
    assert new_task.status_code == 409
    assert new_task.json()["detail"]["code"] == "project_not_open_for_tasks"


def test_goal_cannot_finish_while_linked_project_is_open(client):
    goal = create_goal(client)
    client.post(
        "/api/v1/projects",
        json={"title": "진행 중 프로젝트", "goal_id": goal["id"]},
    )

    response = client.post(
        f"/api/v1/goals/{goal['id']}/transition",
        json={"status": "achieved"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "goal_has_open_projects"
