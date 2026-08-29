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
