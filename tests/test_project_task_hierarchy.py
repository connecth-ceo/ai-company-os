def create_project(client, *, tenant="owner", title="JARVIS Foundation"):
    response = client.post(
        "/api/v1/projects",
        json={"title": title, "description": "점진적 Company OS 확장"},
        headers={"X-Tenant-ID": tenant},
    )
    assert response.status_code == 201
    return response.json()


def test_project_crud_is_tenant_isolated(client):
    project = create_project(client)

    detail = client.get(f"/api/v1/projects/{project['id']}")
    hidden = client.get(f"/api/v1/projects/{project['id']}", headers={"X-Tenant-ID": "other"})

    assert detail.status_code == 200
    assert detail.json()["status"] == "active"
    assert hidden.status_code == 404
    assert client.get("/api/v1/projects").json()[0]["id"] == project["id"]
    assert client.get("/api/v1/projects", headers={"X-Tenant-ID": "other"}).json() == []

    events = client.get("/api/v1/audit-events").json()
    assert any(
        event["action"] == "project.created" and event["resource_id"] == project["id"]
        for event in events
    )


def test_task_can_belong_to_project_and_parent_task(client):
    project = create_project(client)
    parent = client.post(
        "/api/v1/tasks",
        json={
            "title": "시장 진입 프로젝트",
            "request": "시장 진입 전략을 구성해줘.",
            "project_id": project["id"],
        },
    )
    assert parent.status_code == 201

    child = client.post(
        "/api/v1/tasks",
        json={
            "title": "경쟁사 조사",
            "request": "주요 경쟁사를 조사해줘.",
            "project_id": project["id"],
            "parent_task_id": parent.json()["id"],
        },
    )

    assert child.status_code == 201
    assert child.json()["project_id"] == project["id"]
    assert child.json()["parent_task_id"] == parent.json()["id"]

    dispatched = client.post(f"/api/v1/tasks/{child.json()['id']}/run")
    detail = client.get(f"/api/v1/tasks/{child.json()['id']}")
    assert dispatched.status_code == 202
    assert detail.json()["status"] == "completed"


def test_task_relationships_reject_missing_cross_tenant_and_mismatched_project(client):
    owner_project = create_project(client, title="Owner project")
    other_project = create_project(client, tenant="other", title="Other project")
    parent = client.post(
        "/api/v1/tasks",
        json={
            "title": "Parent",
            "request": "부모 업무",
            "project_id": owner_project["id"],
        },
    ).json()

    missing = client.post(
        "/api/v1/tasks",
        json={"title": "Missing", "request": "없는 프로젝트", "project_id": "missing"},
    )
    cross_tenant = client.post(
        "/api/v1/tasks",
        json={
            "title": "Cross tenant",
            "request": "다른 회사 프로젝트",
            "project_id": other_project["id"],
        },
    )
    no_parent_project = client.post(
        "/api/v1/tasks",
        json={"title": "No project", "request": "프로젝트 누락", "parent_task_id": parent["id"]},
    )
    second_project = create_project(client, title="Second project")
    mismatched = client.post(
        "/api/v1/tasks",
        json={
            "title": "Mismatch",
            "request": "프로젝트 불일치",
            "project_id": second_project["id"],
            "parent_task_id": parent["id"],
        },
    )

    assert missing.status_code == 404
    assert cross_tenant.status_code == 404
    assert no_parent_project.status_code == 409
    assert mismatched.status_code == 409


def test_existing_task_payload_remains_backward_compatible(client):
    response = client.post(
        "/api/v1/tasks",
        json={"title": "기존 업무", "request": "기존 형식 그대로 실행해줘."},
    )

    assert response.status_code == 201
    assert response.json()["project_id"] is None
    assert response.json()["parent_task_id"] is None
