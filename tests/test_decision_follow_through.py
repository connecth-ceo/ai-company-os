from datetime import UTC, datetime, timedelta


def create_decision(client, subject: str, *, tenant: str = "owner", **overrides) -> dict:
    payload = {
        "subject": subject,
        "choice": "실행 기준을 적용한다.",
        "rationale": "대표의 실행 판단",
    }
    payload.update(overrides)
    response = client.post(
        "/api/v1/decisions",
        headers={"X-Tenant-ID": tenant},
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def create_commitment(
    client,
    decision_id: str,
    *,
    tenant: str = "owner",
    due_at: datetime | None = None,
    status: str = "open",
) -> dict:
    response = client.post(
        "/api/v1/commitments",
        headers={"X-Tenant-ID": tenant},
        json={
            "statement": "결정의 후속 실행을 완료한다.",
            "owner_id": "CEO",
            "due_at": (due_at or datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "status": status,
            "source_type": "decision",
            "decision_id": decision_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def transition_commitment(client, commitment_id: str, status: str) -> dict:
    response = client.post(
        f"/api/v1/commitments/{commitment_id}/transition",
        json={"status": status, "note": "후속 실행 상태 확인"},
    )
    assert response.status_code == 200
    return response.json()


def test_follow_through_classifies_active_decision_execution(client):
    now = datetime.now(UTC)
    untracked = create_decision(client, "후속 약속 없는 결정")
    overdue = create_decision(client, "기한 초과 실행 결정")
    create_commitment(client, overdue["id"], due_at=now - timedelta(minutes=1))
    planned = create_decision(client, "실행 계획 결정")
    create_commitment(client, planned["id"], due_at=now + timedelta(days=3))
    running = create_decision(client, "진행 중 실행 결정")
    create_commitment(
        client,
        running["id"],
        due_at=now + timedelta(days=2),
        status="in_progress",
    )
    complete = create_decision(client, "실행 완료 결정")
    completed_commitment = create_commitment(client, complete["id"])
    transition_commitment(client, completed_commitment["id"], "completed")
    inactive = create_decision(client, "철회된 결정")
    assert (
        client.post(
            f"/api/v1/decisions/{inactive['id']}/transition",
            json={"status": "revoked", "note": "실행 중단"},
        ).status_code
        == 200
    )

    response = client.get("/api/v1/decisions/follow-through")

    assert response.status_code == 200
    body = response.json()
    assert body["rule_version"] == "decision-follow-through-v1"
    assert body["summary"]["active_decisions"] == 5
    assert body["summary"]["linked_decisions"] == 4
    assert body["summary"]["execution_coverage_percent"] == 80
    assert body["summary"]["follow_through_counts"] == {
        "untracked": 1,
        "at_risk": 1,
        "planned": 1,
        "in_progress": 1,
        "complete": 1,
        "inactive": 1,
    }
    assert [item["follow_through_level"] for item in body["items"]] == [
        "at_risk",
        "untracked",
        "in_progress",
        "planned",
    ]
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[overdue["id"]]["follow_through_reason"] == "overdue_commitment"
    assert by_id[overdue["id"]]["overdue_commitments"] == 1
    assert by_id[untracked["id"]]["follow_through_reason"] == "no_commitment"
    assert complete["id"] not in by_id
    assert inactive["id"] not in by_id


def test_follow_through_includes_complete_inactive_and_cancelled_only(client):
    cancelled = create_decision(client, "취소만 남은 결정")
    cancelled_commitment = create_commitment(client, cancelled["id"])
    transition_commitment(client, cancelled_commitment["id"], "cancelled")
    complete = create_decision(client, "완료된 결정")
    complete_commitment = create_commitment(client, complete["id"])
    transition_commitment(client, complete_commitment["id"], "completed")
    inactive = create_decision(client, "비활성 결정", status="proposed")

    body = client.get(
        "/api/v1/decisions/follow-through?include_complete=true&include_inactive=true"
    ).json()
    by_id = {item["id"]: item for item in body["items"]}

    assert by_id[cancelled["id"]]["follow_through_level"] == "at_risk"
    assert by_id[cancelled["id"]]["follow_through_reason"] == "cancelled_only"
    assert by_id[complete["id"]]["follow_through_level"] == "complete"
    assert by_id[complete["id"]]["commitment_counts"]["completed"] == 1
    assert by_id[inactive["id"]]["follow_through_level"] == "inactive"
    assert by_id[inactive["id"]]["follow_through_reason"] == "decision_not_active"


def test_follow_through_is_read_only_tenant_safe_and_limit_safe(client):
    first = create_decision(client, "첫 실행 결정")
    second = create_decision(client, "둘째 실행 결정")
    create_decision(client, "다른 회사 결정", tenant="other")
    before = client.get("/api/v1/audit-events?limit=100").json()

    body = client.get("/api/v1/decisions/follow-through?limit=1").json()
    after = client.get("/api/v1/audit-events?limit=100").json()
    other = client.get(
        "/api/v1/decisions/follow-through",
        headers={"X-Tenant-ID": "other"},
    ).json()

    assert after == before
    assert body["summary"]["total_decisions"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] in {first["id"], second["id"]}
    assert other["summary"]["total_decisions"] == 1
    assert len(other["items"]) == 1
