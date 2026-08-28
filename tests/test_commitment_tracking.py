from datetime import UTC, datetime, timedelta


def commitment_payload(**overrides):
    payload = {
        "statement": "금요일까지 고객 인터뷰 일정을 확정한다.",
        "owner_id": "CEO",
        "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
    }
    payload.update(overrides)
    return payload


def test_commitment_defaults_detail_and_audit(client):
    created = client.post("/api/v1/commitments", json=commitment_payload())

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "open"
    assert body["owner_type"] == "person"
    assert body["source_type"] == "manual"
    assert body["source_id"] is None
    assert body["is_overdue"] is False
    assert body["completed_at"] is None

    detail = client.get(f"/api/v1/commitments/{body['id']}")
    events = client.get("/api/v1/audit-events").json()
    assert detail.status_code == 200
    assert detail.json()["id"] == body["id"]
    assert any(
        event["action"] == "commitment.created" and event["resource_id"] == body["id"]
        for event in events
    )


def test_commitments_are_tenant_isolated(client):
    owner = {"X-Tenant-ID": "owner"}
    other = {"X-Tenant-ID": "other"}
    item = client.post("/api/v1/commitments", json=commitment_payload(), headers=owner).json()

    assert client.get(f"/api/v1/commitments/{item['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/commitments", headers=other).json() == []
    assert len(client.get("/api/v1/commitments", headers=owner).json()) == 1


def test_commitment_links_project_task_and_decision(client):
    project = client.post("/api/v1/projects", json={"title": "Launch"}).json()
    task = client.post(
        "/api/v1/tasks",
        json={
            "title": "Interview",
            "request": "Schedule interviews",
            "project_id": project["id"],
        },
    ).json()
    decision = client.post(
        "/api/v1/decisions",
        json={
            "subject": "Interview target",
            "choice": "Interview five customers",
            "rationale": "Enough for the first signal",
        },
    ).json()

    created = client.post(
        "/api/v1/commitments",
        json=commitment_payload(
            project_id=project["id"],
            task_id=task["id"],
            decision_id=decision["id"],
            source_type="decision",
            provenance={"channel": "ceo_desk"},
            reminder_policy={"lead_hours": "24"},
        ),
    )

    assert created.status_code == 201
    body = created.json()
    assert body["project_id"] == project["id"]
    assert body["task_id"] == task["id"]
    assert body["decision_id"] == decision["id"]
    assert body["source_id"] == decision["id"]
    assert body["provenance"] == {"channel": "ceo_desk"}


def test_commitment_rejects_cross_tenant_and_mismatched_links(client):
    other = {"X-Tenant-ID": "other"}
    other_decision = client.post(
        "/api/v1/decisions",
        headers=other,
        json={"subject": "Other", "choice": "Other", "rationale": "Other"},
    ).json()
    first_project = client.post("/api/v1/projects", json={"title": "First"}).json()
    second_project = client.post("/api/v1/projects", json={"title": "Second"}).json()
    task = client.post(
        "/api/v1/tasks",
        json={
            "title": "First task",
            "request": "work",
            "project_id": first_project["id"],
        },
    ).json()

    cross_tenant = client.post(
        "/api/v1/commitments",
        json=commitment_payload(decision_id=other_decision["id"]),
    )
    mismatch = client.post(
        "/api/v1/commitments",
        json=commitment_payload(project_id=second_project["id"], task_id=task["id"]),
    )

    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["detail"]["code"] == "decision_not_found"
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "project_task_mismatch"


def test_commitment_source_rules_are_explicit(client):
    manual_with_id = client.post(
        "/api/v1/commitments",
        json=commitment_payload(source_id="hidden-source"),
    )
    missing_meeting_id = client.post(
        "/api/v1/commitments",
        json=commitment_payload(source_type="meeting"),
    )
    missing_task_link = client.post(
        "/api/v1/commitments",
        json=commitment_payload(source_type="task"),
    )

    assert manual_with_id.status_code == 409
    assert manual_with_id.json()["detail"]["code"] == "invalid_manual_source"
    assert missing_meeting_id.status_code == 409
    assert missing_meeting_id.json()["detail"]["code"] == "source_id_required"
    assert missing_task_link.status_code == 409
    assert missing_task_link.json()["detail"]["code"] == "invalid_task_source"


def test_commitment_transition_completion_is_terminal_and_audited(client):
    item = client.post("/api/v1/commitments", json=commitment_payload()).json()
    started = client.post(
        f"/api/v1/commitments/{item['id']}/transition",
        json={"status": "in_progress", "note": "담당자 확인"},
    )
    completed = client.post(
        f"/api/v1/commitments/{item['id']}/transition",
        json={"status": "completed", "note": "일정 확정"},
    )
    reopened = client.post(
        f"/api/v1/commitments/{item['id']}/transition",
        json={"status": "open"},
    )

    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None
    assert reopened.status_code == 409
    assert reopened.json()["detail"]["code"] == "invalid_status_transition"
    events = client.get("/api/v1/audit-events").json()
    assert any(event["action"] == "commitment.in_progress" for event in events)
    assert any(event["action"] == "commitment.completed" for event in events)


def test_cancelled_commitment_is_terminal(client):
    item = client.post("/api/v1/commitments", json=commitment_payload()).json()
    cancelled = client.post(
        f"/api/v1/commitments/{item['id']}/transition",
        json={"status": "cancelled", "note": "더 이상 필요 없음"},
    )
    completed = client.post(
        f"/api/v1/commitments/{item['id']}/transition",
        json={"status": "completed"},
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["completed_at"] is None
    assert completed.status_code == 409


def test_overdue_is_derived_and_overdue_filter_excludes_closed_items(client):
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    overdue = client.post(
        "/api/v1/commitments", json=commitment_payload(statement="Overdue", due_at=past)
    ).json()
    closed = client.post(
        "/api/v1/commitments", json=commitment_payload(statement="Closed", due_at=past)
    ).json()
    client.post(
        f"/api/v1/commitments/{closed['id']}/transition",
        json={"status": "completed"},
    )

    detail = client.get(f"/api/v1/commitments/{overdue['id']}").json()
    filtered = client.get("/api/v1/commitments?overdue_only=true").json()

    assert detail["is_overdue"] is True
    assert [item["id"] for item in filtered] == [overdue["id"]]
    assert client.get(f"/api/v1/commitments/{closed['id']}").json()["is_overdue"] is False


def test_commitment_filters_by_owner_status_and_links(client):
    decision = client.post(
        "/api/v1/decisions",
        json={"subject": "Plan", "choice": "Go", "rationale": "Evidence"},
    ).json()
    first = client.post(
        "/api/v1/commitments",
        json=commitment_payload(owner_id="CEO", decision_id=decision["id"]),
    ).json()
    second = client.post(
        "/api/v1/commitments",
        json=commitment_payload(owner_id="Research Agent", owner_type="agent"),
    ).json()
    client.post(
        f"/api/v1/commitments/{second['id']}/transition",
        json={"status": "in_progress"},
    )

    by_owner = client.get("/api/v1/commitments?owner_id=CEO").json()
    by_status = client.get("/api/v1/commitments?status=in_progress").json()
    by_decision = client.get(f"/api/v1/commitments?decision_id={decision['id']}").json()

    assert [item["id"] for item in by_owner] == [first["id"]]
    assert [item["id"] for item in by_status] == [second["id"]]
    assert [item["id"] for item in by_decision] == [first["id"]]


def test_commitment_initial_and_metadata_inputs_are_bounded(client):
    completed = client.post("/api/v1/commitments", json=commitment_payload(status="completed"))
    too_many = client.post(
        "/api/v1/commitments",
        json=commitment_payload(provenance={f"key-{i}": "value" for i in range(21)}),
    )
    blank = client.post(
        "/api/v1/commitments",
        json=commitment_payload(statement="   ", owner_id="   "),
    )

    assert completed.status_code == 409
    assert completed.json()["detail"]["code"] == "invalid_initial_status"
    assert too_many.status_code == 409
    assert too_many.json()["detail"]["code"] == "invalid_provenance"
    assert blank.status_code == 409
    assert blank.json()["detail"]["code"] == "blank_required_field"
