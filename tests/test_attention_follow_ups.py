from datetime import UTC, datetime, timedelta


def overdue_commitment_payload(statement: str, *, hours: int = 2) -> dict[str, str]:
    return {
        "statement": statement,
        "owner_id": "CEO",
        "due_at": (datetime.now(UTC) - timedelta(hours=hours)).isoformat(),
    }


def follow_up_payload(fingerprint: str, idempotency_key: str) -> dict[str, str]:
    return {
        "expected_fingerprint": fingerprint,
        "owner_type": "agent",
        "owner_id": "chief_of_staff",
        "note": "자동화 전 안전한 내부 후속조치",
        "idempotency_key": idempotency_key,
    }


def test_attention_follow_up_creates_linked_task_and_commitment_without_execution(client):
    original = client.post(
        "/api/v1/commitments",
        json=overdue_commitment_payload("고객 응답 지연 확인"),
    ).json()
    attention = client.get("/api/v1/attention?kind=overdue_commitment").json()["items"][0]

    response = client.post(
        f"/api/v1/attention/{attention['id']}/follow-ups",
        json=follow_up_payload(attention["fingerprint"], "attention-follow-up-001"),
    )

    assert response.status_code == 201
    follow_up = response.json()
    assert follow_up["attention_id"] == attention["id"]
    assert follow_up["fingerprint"] == attention["fingerprint"]
    assert follow_up["task_status"] == "queued"
    assert follow_up["commitment_status"] == "open"
    assert follow_up["status"] == "planned"

    task = client.get(f"/api/v1/tasks/{follow_up['task_id']}").json()
    assert task["source"] == "attention"
    assert task["status"] == "queued"
    assert task["runs"] == []
    assert task["title"].startswith("주의 대응:")

    commitment = client.get(f"/api/v1/commitments/{follow_up['commitment_id']}").json()
    assert commitment["task_id"] == task["id"]
    assert commitment["source_type"] == "task"
    assert commitment["owner_type"] == "agent"
    assert commitment["owner_id"] == "chief_of_staff"
    assert commitment["provenance"]["attention_id"] == attention["id"]
    assert commitment["provenance"]["attention_fingerprint"] == attention["fingerprint"]
    due_at = datetime.fromisoformat(commitment["due_at"])
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=UTC)
    due_delta = due_at - datetime.now(UTC)
    assert timedelta(hours=23, minutes=55) < due_delta <= timedelta(hours=24)

    queue = client.get("/api/v1/attention?kind=overdue_commitment").json()
    item = next(item for item in queue["items"] if item["resource_id"] == original["id"])
    assert item["acknowledged"] is True
    assert item["follow_up_id"] == follow_up["id"]
    assert item["follow_up_task_id"] == task["id"]
    assert item["follow_up_commitment_id"] == commitment["id"]
    assert item["follow_up_status"] == "planned"
    assert client.get("/api/v1/attention?include_acknowledged=false").json()["total"] == 0


def test_attention_follow_up_is_idempotent_tenant_safe_and_tracks_completion(client):
    client.post(
        "/api/v1/commitments",
        json=overdue_commitment_payload("계약 후속 확인"),
    )
    attention = client.get("/api/v1/attention").json()["items"][0]
    payload = follow_up_payload(attention["fingerprint"], "attention-follow-up-002")
    created = client.post(
        f"/api/v1/attention/{attention['id']}/follow-ups",
        json=payload,
    ).json()

    repeated = client.post(
        f"/api/v1/attention/{attention['id']}/follow-ups",
        json=payload,
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == created["id"]

    history = client.get(
        "/api/v1/attention/follow-ups",
        params={"attention_id": attention["id"]},
    ).json()
    assert [item["id"] for item in history] == [created["id"]]
    assert (
        client.get(
            "/api/v1/attention/follow-ups",
            headers={"X-Tenant-ID": "other"},
        ).json()
        == []
    )
    cross_tenant = client.post(
        f"/api/v1/attention/{attention['id']}/follow-ups",
        headers={"X-Tenant-ID": "other"},
        json={**payload, "idempotency_key": "attention-follow-up-other"},
    )
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["detail"]["code"] == "attention_not_found"

    completed = client.post(
        f"/api/v1/commitments/{created['commitment_id']}/transition",
        json={"status": "completed", "note": "후속조치 완료"},
    )
    assert completed.status_code == 200
    refreshed = client.get(
        "/api/v1/attention/follow-ups",
        params={"attention_id": attention["id"]},
    ).json()[0]
    assert refreshed["commitment_status"] == "completed"
    assert refreshed["status"] == "completed"


def test_attention_follow_up_rejects_stale_fingerprint_and_conflicting_requests(client):
    client.post(
        "/api/v1/commitments",
        json=overdue_commitment_payload("충돌 검사"),
    )
    attention = client.get("/api/v1/attention").json()["items"][0]

    stale = client.post(
        f"/api/v1/attention/{attention['id']}/follow-ups",
        json=follow_up_payload("0" * 64, "attention-follow-up-stale"),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "attention_fingerprint_mismatch"

    payload = follow_up_payload(attention["fingerprint"], "attention-follow-up-003")
    created = client.post(
        f"/api/v1/attention/{attention['id']}/follow-ups",
        json=payload,
    )
    assert created.status_code == 201

    idempotency_conflict = client.post(
        f"/api/v1/attention/{attention['id']}/follow-ups",
        json={**payload, "due_in_hours": 48},
    )
    assert idempotency_conflict.status_code == 409
    assert idempotency_conflict.json()["detail"]["code"] == "idempotency_conflict"

    signal_conflict = client.post(
        f"/api/v1/attention/{attention['id']}/follow-ups",
        json={**payload, "idempotency_key": "attention-follow-up-004", "due_in_hours": 48},
    )
    assert signal_conflict.status_code == 409
    assert signal_conflict.json()["detail"]["code"] == "follow_up_already_exists"


def test_decision_attention_follow_up_preserves_decision_link(client):
    decision = client.post(
        "/api/v1/decisions",
        json={
            "subject": "신규 가격 정책",
            "choice": "근거 검토 후 적용한다.",
            "rationale": "결정 후속조치 연결 검사",
        },
    ).json()
    attention = client.get("/api/v1/attention?kind=decision_governance").json()["items"][0]

    follow_up = client.post(
        f"/api/v1/attention/{attention['id']}/follow-ups",
        json=follow_up_payload(attention["fingerprint"], "attention-follow-up-decision"),
    )

    assert follow_up.status_code == 201
    commitment = client.get(f"/api/v1/commitments/{follow_up.json()['commitment_id']}").json()
    assert commitment["decision_id"] == decision["id"]
    assert commitment["task_id"] == follow_up.json()["task_id"]
    changed = client.get("/api/v1/attention?kind=decision_governance").json()["items"][0]
    assert changed["fingerprint"] != attention["fingerprint"]
    assert changed["acknowledged"] is False
    assert changed["follow_up_id"] == follow_up.json()["id"]
    assert changed["follow_up_matches_current_signal"] is False
