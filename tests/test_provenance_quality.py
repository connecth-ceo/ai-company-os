from tests.test_provenance import create_and_run_task


def create_manual_decision(client, subject: str, *, tenant: str = "owner") -> dict:
    response = client.post(
        "/api/v1/decisions",
        headers={"X-Tenant-ID": tenant},
        json={
            "subject": subject,
            "choice": "수동 판단",
            "rationale": "대표의 운영 판단",
        },
    )
    assert response.status_code == 201
    return response.json()


def review_record(client, record: dict, decision: str, key: str) -> dict:
    response = client.post(
        f"/api/v1/provenance/{record['id']}/reviews",
        json={
            "decision": decision,
            "expected_content_hash": record["content_hash"],
            "reviewed_by": "CEO",
            "note": "품질 큐 검증" if decision == "verified" else "근거 부적합",
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_provenance_quality_prioritizes_rejected_and_unverified_decisions(client):
    task = create_and_run_task(
        client,
        "https://example.com/quality-source 를 근거로 검토해줘.",
    )
    observed = client.get(f"/api/v1/provenance?task_id={task['id']}").json()[0]
    decision = create_manual_decision(client, "품질 큐 우선순위")
    unverified = client.get(f"/api/v1/provenance?decision_id={decision['id']}").json()[0]
    review_record(client, observed, "rejected", "quality-rejected-001")

    response = client.get("/api/v1/provenance/quality")

    assert response.status_code == 200
    body = response.json()
    assert body["rule_version"] == "provenance-quality-v1"
    assert [item["id"] for item in body["items"]] == [observed["id"], unverified["id"]]
    assert body["items"][0]["quality_reason"] == "rejected"
    assert body["items"][0]["quality_level"] == "critical"
    assert body["items"][0]["review_count"] == 1
    assert body["items"][0]["latest_reviewed_at"] is not None
    assert body["items"][1]["quality_reason"] == "unverified_decision"
    assert body["summary"] == {
        "total_records": 2,
        "verified_records": 0,
        "rejected_records": 1,
        "needs_review_records": 1,
        "verification_coverage_percent": 0,
        "quality_counts": {"healthy": 0, "watch": 0, "action": 0, "critical": 2},
    }


def test_provenance_quality_coverage_is_read_only_and_tenant_safe(client):
    first = create_manual_decision(client, "검증할 결정")
    second = create_manual_decision(client, "대기할 결정")
    create_manual_decision(client, "다른 회사 결정", tenant="other")
    verified = client.get(f"/api/v1/provenance?decision_id={first['id']}").json()[0]
    waiting = client.get(f"/api/v1/provenance?decision_id={second['id']}").json()[0]
    review_record(client, verified, "verified", "quality-verified-001")
    before = client.get("/api/v1/audit-events?limit=100").json()

    body = client.get("/api/v1/provenance/quality?limit=1").json()
    after = client.get("/api/v1/audit-events?limit=100").json()

    assert after == before
    assert body["summary"]["total_records"] == 2
    assert body["summary"]["verified_records"] == 1
    assert body["summary"]["needs_review_records"] == 1
    assert body["summary"]["verification_coverage_percent"] == 50
    assert [item["id"] for item in body["items"]] == [waiting["id"]]

    included = client.get("/api/v1/provenance/quality?include_verified=true&limit=10").json()
    assert [item["id"] for item in included["items"]] == [waiting["id"], verified["id"]]
    assert included["items"][1]["quality_level"] == "healthy"
    assert included["items"][1]["quality_reason"] == "verified"

    other = client.get(
        "/api/v1/provenance/quality",
        headers={"X-Tenant-ID": "other"},
    ).json()
    assert other["summary"]["total_records"] == 1
    assert len(other["items"]) == 1
