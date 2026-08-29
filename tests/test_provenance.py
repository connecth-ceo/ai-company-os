from app.services.provenance import extract_source_uris


def create_and_run_task(client, request: str) -> dict:
    created = client.post(
        "/api/v1/tasks",
        json={"title": "Provenance test", "request": request},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    dispatched = client.post(f"/api/v1/tasks/{task_id}/run")
    assert dispatched.status_code == 202
    detail = client.get(f"/api/v1/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"
    return detail.json()


def test_extract_source_uris_is_bounded_normalized_and_deduplicated():
    content = (
        "See HTTPS://Example.COM/report?q=1#section and "
        "https://example.com/report?q=1. Invalid ftp://example.com/file."
    )

    assert extract_source_uris(content) == ["https://example.com/report?q=1"]


def test_research_provenance_is_captured_and_tenant_safe(client):
    task = create_and_run_task(
        client,
        "근거 https://Example.com/report#summary 를 포함해 검토해줘.",
    )

    response = client.get(f"/api/v1/provenance?task_id={task['id']}")
    assert response.status_code == 200
    records = response.json()
    assert len(records) == 1
    record = records[0]
    assert record["subject_type"] == "knowledge"
    assert record["source_type"] == "url"
    assert record["source_uri"] == "https://example.com/report"
    assert record["claim_reference"] == "research_brief"
    assert record["verification_status"] == "observed"
    assert record["task_run_id"] == task["runs"][0]["id"]
    assert len(record["content_hash"]) == 64
    assert record["record_metadata"]["citation_count"] == 1

    hidden_list = client.get(
        "/api/v1/provenance",
        headers={"X-Tenant-ID": "other"},
    )
    hidden_detail = client.get(
        f"/api/v1/provenance/{record['id']}",
        headers={"X-Tenant-ID": "other"},
    )
    assert hidden_list.json() == []
    assert hidden_detail.status_code == 404


def test_decision_inherits_task_research_provenance(client):
    task = create_and_run_task(
        client,
        "https://example.com/source 를 근거로 선택지를 검토해줘.",
    )
    knowledge_record = client.get(
        f"/api/v1/provenance?task_id={task['id']}&subject_type=knowledge"
    ).json()[0]

    created = client.post(
        "/api/v1/decisions",
        json={
            "subject": "출시 방식",
            "choice": "단계적 출시",
            "rationale": "연구 결과에 따라 위험을 줄이는 방식을 선택한다.",
            "task_id": task["id"],
        },
    )
    assert created.status_code == 201

    records = client.get(f"/api/v1/provenance?decision_id={created.json()['id']}").json()
    assert len(records) == 1
    record = records[0]
    assert record["subject_type"] == "decision"
    assert record["source_type"] == "inherited"
    assert record["source_record_id"] == knowledge_record["id"]
    assert record["source_uri"] == "https://example.com/source"
    assert record["claim_reference"] == "decision_rationale"


def test_manual_decision_records_unverified_rationale(client):
    created = client.post(
        "/api/v1/decisions",
        json={
            "subject": "내부 운영 방식",
            "choice": "주간 검토",
            "rationale": "대표의 운영 판단",
        },
    )

    records = client.get(f"/api/v1/provenance?decision_id={created.json()['id']}").json()
    assert len(records) == 1
    assert records[0]["source_type"] == "manual"
    assert records[0]["verification_status"] == "unverified"


def test_provenance_review_is_hash_bound_idempotent_and_audited(client):
    task = create_and_run_task(
        client,
        "https://example.com/review-source 를 근거로 검토해줘.",
    )
    record = client.get(f"/api/v1/provenance?task_id={task['id']}").json()[0]
    payload = {
        "decision": "verified",
        "expected_content_hash": record["content_hash"],
        "reviewed_by": "CEO",
        "note": "원문과 연구 요약을 대조함",
        "idempotency_key": "provenance-review-001",
    }

    reviewed = client.post(f"/api/v1/provenance/{record['id']}/reviews", json=payload)

    assert reviewed.status_code == 201
    review = reviewed.json()
    assert review["decision"] == "verified"
    assert review["previous_status"] == "observed"
    assert review["reviewed_content_hash"] == record["content_hash"]
    repeated = client.post(f"/api/v1/provenance/{record['id']}/reviews", json=payload)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == review["id"]

    detail = client.get(f"/api/v1/provenance/{record['id']}")
    history = client.get(f"/api/v1/provenance/{record['id']}/reviews")
    events = client.get("/api/v1/audit-events?limit=20").json()
    assert detail.json()["verification_status"] == "verified"
    assert [item["id"] for item in history.json()] == [review["id"]]
    assert any(
        event["action"] == "provenance.verified"
        and event["details"]["review_id"] == review["id"]
        and event["details"]["content_hash"] == record["content_hash"]
        for event in events
    )

    conflict_payload = {**payload, "decision": "rejected", "note": "다른 요청"}
    conflict = client.post(
        f"/api/v1/provenance/{record['id']}/reviews",
        json=conflict_payload,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"


def test_provenance_review_rejects_stale_hash_and_cross_tenant_access(client):
    task = create_and_run_task(
        client,
        "https://example.com/hash-source 를 근거로 검토해줘.",
    )
    record = client.get(f"/api/v1/provenance?task_id={task['id']}").json()[0]
    payload = {
        "decision": "verified",
        "expected_content_hash": "0" * 64,
        "reviewed_by": "CEO",
        "idempotency_key": "provenance-review-stale",
    }

    stale = client.post(f"/api/v1/provenance/{record['id']}/reviews", json=payload)
    hidden_list = client.get(
        f"/api/v1/provenance/{record['id']}/reviews",
        headers={"X-Tenant-ID": "other"},
    )
    hidden_review = client.post(
        f"/api/v1/provenance/{record['id']}/reviews",
        json={**payload, "expected_content_hash": record["content_hash"]},
        headers={"X-Tenant-ID": "other"},
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "content_hash_mismatch"
    assert (
        client.get(f"/api/v1/provenance/{record['id']}").json()["verification_status"] == "observed"
    )
    assert hidden_list.status_code == 404
    assert hidden_review.status_code == 404


def test_provenance_review_corrections_preserve_history_and_require_notes(client):
    created = client.post(
        "/api/v1/decisions",
        json={
            "subject": "검토 정책",
            "choice": "수동 검토",
            "rationale": "대표의 운영 판단",
        },
    )
    record = client.get(f"/api/v1/provenance?decision_id={created.json()['id']}").json()[0]
    verified = client.post(
        f"/api/v1/provenance/{record['id']}/reviews",
        json={
            "decision": "verified",
            "expected_content_hash": record["content_hash"],
            "reviewed_by": "CEO",
            "idempotency_key": "provenance-review-correction-1",
        },
    )
    missing_rejection_note = client.post(
        f"/api/v1/provenance/{record['id']}/reviews",
        json={
            "decision": "rejected",
            "expected_content_hash": record["content_hash"],
            "reviewed_by": "CEO",
            "idempotency_key": "provenance-review-correction-2",
        },
    )
    corrected = client.post(
        f"/api/v1/provenance/{record['id']}/reviews",
        json={
            "decision": "rejected",
            "expected_content_hash": record["content_hash"],
            "reviewed_by": "CEO",
            "note": "추가 확인 결과 내부 판단을 근거에서 제외",
            "idempotency_key": "provenance-review-correction-3",
        },
    )
    missing_correction_note = client.post(
        f"/api/v1/provenance/{record['id']}/reviews",
        json={
            "decision": "verified",
            "expected_content_hash": record["content_hash"],
            "reviewed_by": "CEO",
            "idempotency_key": "provenance-review-correction-4",
        },
    )

    assert verified.status_code == 201
    assert missing_rejection_note.status_code == 422
    assert corrected.status_code == 201
    assert corrected.json()["previous_status"] == "verified"
    assert missing_correction_note.status_code == 409
    assert missing_correction_note.json()["detail"]["code"] == "correction_note_required"
    history = client.get(f"/api/v1/provenance/{record['id']}/reviews").json()
    assert [item["decision"] for item in history] == ["rejected", "verified"]
    assert (
        client.get(f"/api/v1/provenance/{record['id']}").json()["verification_status"] == "rejected"
    )
