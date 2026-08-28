from datetime import UTC, datetime, timedelta


def decision_payload(**overrides):
    payload = {
        "subject": "시장 우선순위",
        "choice": "한국 시장을 먼저 검증한다.",
        "rationale": "초기 고객 접근성이 가장 높다.",
    }
    payload.update(overrides)
    return payload


def run_context_probe(client, title: str = "결정 맥락 확인", **task_fields) -> dict:
    payload = {
        "title": title,
        "request": "현재 회사 결정을 반영해 실행안을 작성해줘.",
    }
    payload.update(task_fields)
    task = client.post(
        "/api/v1/tasks",
        json=payload,
    ).json()
    dispatched = client.post(f"/api/v1/tasks/{task['id']}/run")
    assert dispatched.status_code == 202
    return client.get(f"/api/v1/tasks/{task['id']}").json()


def test_legacy_decision_payload_gets_safe_lifecycle_defaults(client):
    created = client.post("/api/v1/decisions", json=decision_payload())

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "active"
    assert body["scope"] == "company"
    assert body["applies_to"] == {}
    assert body["effective_at"]
    assert body["expires_at"] is None
    assert body["review_due_at"] is None
    assert body["supersedes_decision_id"] is None

    detail = client.get(f"/api/v1/decisions/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == body["id"]


def test_decisions_are_tenant_isolated(client):
    owner = {"X-Tenant-ID": "owner"}
    other = {"X-Tenant-ID": "other"}
    decision = client.post(
        "/api/v1/decisions",
        json=decision_payload(),
        headers=owner,
    ).json()

    assert client.get(f"/api/v1/decisions/{decision['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/decisions", headers=other).json() == []
    assert len(client.get("/api/v1/decisions", headers=owner).json()) == 1


def test_decision_scope_target_is_exact_and_tenant_safe(client):
    owner = {"X-Tenant-ID": "owner"}
    other = {"X-Tenant-ID": "other"}
    owner_project = client.post(
        "/api/v1/projects",
        json={"title": "Owner project"},
        headers=owner,
    ).json()
    other_project = client.post(
        "/api/v1/projects",
        json={"title": "Other project"},
        headers=other,
    ).json()

    scoped = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            scope="project",
            applies_to={"project_id": owner_project["id"]},
        ),
        headers=owner,
    )
    cross_tenant = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            scope="project",
            applies_to={"project_id": other_project["id"]},
        ),
        headers=owner,
    )
    extra_target = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            scope="department",
            applies_to={"department": "marketing", "extra": "not-allowed"},
        ),
        headers=owner,
    )

    assert scoped.status_code == 201
    assert scoped.json()["applies_to"] == {"project_id": owner_project["id"]}
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["detail"]["code"] == "scope_target_not_found"
    assert extra_target.status_code == 409
    assert extra_target.json()["detail"]["code"] == "invalid_scope_target"


def test_project_decision_only_reaches_tasks_in_that_project(client):
    project = client.post(
        "/api/v1/projects",
        json={"title": "Scoped project"},
    ).json()
    created = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            scope="project",
            applies_to={"project_id": project["id"]},
        ),
    )
    probe = run_context_probe(
        client,
        "Project 범위 포함 확인",
        project_id=project["id"],
    )

    assert created.status_code == 201
    assert probe["runs"][0]["artifacts"]["company_context_used"] is True


def test_project_decision_does_not_reach_unrelated_tasks(client):
    project = client.post(
        "/api/v1/projects",
        json={"title": "Scoped project"},
    ).json()
    client.post(
        "/api/v1/decisions",
        json=decision_payload(
            scope="project",
            applies_to={"project_id": project["id"]},
        ),
    )
    probe = run_context_probe(client, "Project 범위 제외 확인")

    assert probe["runs"][0]["artifacts"]["company_context_used"] is False


def test_task_decision_only_reaches_its_target_task(client):
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Target task", "request": "Task 범위 결정을 확인해줘."},
    ).json()
    created = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            scope="task",
            applies_to={"task_id": task["id"]},
        ),
    )
    dispatched = client.post(f"/api/v1/tasks/{task['id']}/run")
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()

    assert created.status_code == 201
    assert dispatched.status_code == 202
    assert detail["runs"][0]["artifacts"]["company_context_used"] is True


def test_only_current_active_decisions_reach_later_ai_tasks(client):
    proposed = client.post(
        "/api/v1/decisions",
        json=decision_payload(status="proposed"),
    ).json()
    first_probe = run_context_probe(client, "제안 상태 제외 확인")
    activated = client.post(
        f"/api/v1/decisions/{proposed['id']}/transition",
        json={"status": "active", "note": "대표 확정"},
    )
    second_probe = run_context_probe(client, "활성 상태 포함 확인")

    assert first_probe["runs"][0]["artifacts"]["company_context_used"] is False
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    assert second_probe["runs"][0]["artifacts"]["company_context_used"] is True


def test_revoked_and_future_decisions_are_not_effective(client):
    active = client.post("/api/v1/decisions", json=decision_payload()).json()
    revoked = client.post(
        f"/api/v1/decisions/{active['id']}/transition",
        json={"status": "revoked", "note": "전략 변경"},
    )
    future = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            subject="차기 분기 정책",
            effective_at=(datetime.now(UTC) + timedelta(days=7)).isoformat(),
        ),
    )
    probe = run_context_probe(client)

    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert future.status_code == 201
    assert probe["runs"][0]["artifacts"]["company_context_used"] is False
    assert client.get("/api/v1/decisions?effective_only=true").json() == []


def test_active_replacement_supersedes_one_matching_decision(client):
    old = client.post("/api/v1/decisions", json=decision_payload()).json()
    replacement = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            subject="시장 우선순위 개정",
            choice="일본 시장을 먼저 검증한다.",
            supersedes_decision_id=old["id"],
        ),
    )
    repeated = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            subject="잘못된 재대체",
            supersedes_decision_id=old["id"],
        ),
    )

    assert replacement.status_code == 201
    new = replacement.json()
    assert new["supersedes_decision_id"] == old["id"]
    assert client.get(f"/api/v1/decisions/{old['id']}").json()["status"] == "superseded"
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["code"] == "superseded_decision_not_active"

    effective = client.get("/api/v1/decisions?effective_only=true").json()
    assert [item["id"] for item in effective] == [new["id"]]
    events = client.get("/api/v1/audit-events").json()
    assert any(event["action"] == "decision.superseded" for event in events)
    assert any(event["action"] == "decision.created" for event in events)


def test_expiration_and_terminal_transition_rules(client):
    now = datetime.now(UTC)
    invalid = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            effective_at=now.isoformat(),
            expires_at=(now - timedelta(minutes=1)).isoformat(),
        ),
    )
    expired_candidate = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            effective_at=(now - timedelta(days=1)).isoformat(),
            expires_at=(now - timedelta(hours=1)).isoformat(),
        ),
    ).json()
    expired = client.post(
        f"/api/v1/decisions/{expired_candidate['id']}/transition",
        json={"status": "expired"},
    )
    reactivated = client.post(
        f"/api/v1/decisions/{expired_candidate['id']}/transition",
        json={"status": "active"},
    )

    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "invalid_expiration"
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"
    assert reactivated.status_code == 409
    assert reactivated.json()["detail"]["code"] == "invalid_status_transition"


def test_decision_filters_and_initial_status_are_bounded(client):
    company = client.post("/api/v1/decisions", json=decision_payload()).json()
    department = client.post(
        "/api/v1/decisions",
        json=decision_payload(
            subject="마케팅 메시지",
            scope="department",
            applies_to={"department": "marketing"},
            status="proposed",
        ),
    ).json()
    invalid_initial = client.post(
        "/api/v1/decisions",
        json=decision_payload(status="revoked"),
    )

    active = client.get("/api/v1/decisions?status=active").json()
    marketing = client.get("/api/v1/decisions?scope=department").json()

    assert [item["id"] for item in active] == [company["id"]]
    assert [item["id"] for item in marketing] == [department["id"]]
    assert invalid_initial.status_code == 409
    assert invalid_initial.json()["detail"]["code"] == "invalid_initial_status"
