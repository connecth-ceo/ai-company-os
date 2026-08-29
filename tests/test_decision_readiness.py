from datetime import UTC, datetime, timedelta


def create_decision(client, subject: str, *, tenant: str = "owner", **overrides) -> dict:
    payload = {
        "subject": subject,
        "choice": "운영 기준을 적용한다.",
        "rationale": "대표의 운영 판단",
    }
    payload.update(overrides)
    response = client.post(
        "/api/v1/decisions",
        headers={"X-Tenant-ID": tenant},
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def review_decision_evidence(client, decision_id: str, verdict: str, key: str) -> None:
    record = client.get(f"/api/v1/provenance?decision_id={decision_id}").json()[0]
    response = client.post(
        f"/api/v1/provenance/{record['id']}/reviews",
        json={
            "decision": verdict,
            "expected_content_hash": record["content_hash"],
            "reviewed_by": "CEO",
            "note": "근거 부적합" if verdict == "rejected" else "근거 확인 완료",
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201


def test_decision_readiness_prioritizes_blocked_review_and_watch(client):
    now = datetime.now(UTC)
    expired = create_decision(
        client,
        "만료된 활성 결정",
        effective_at=(now - timedelta(days=2)).isoformat(),
        expires_at=(now - timedelta(minutes=1)).isoformat(),
    )
    rejected = create_decision(client, "반려 근거 결정")
    review_decision_evidence(client, rejected["id"], "rejected", "readiness-reject-001")
    proposed = create_decision(client, "대표 검토 대기", status="proposed")
    observed = create_decision(
        client,
        "관찰 근거 결정",
        rationale="https://example.com/source 를 참고한 판단",
    )

    response = client.get("/api/v1/decisions/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["rule_version"] == "decision-readiness-v1"
    assert body["summary"]["total_decisions"] == 4
    assert body["summary"]["readiness_counts"] == {
        "ready": 0,
        "watch": 1,
        "review": 1,
        "blocked": 2,
        "closed": 0,
    }
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[expired["id"]]["readiness_reason"] == "expiration_overdue"
    assert by_id[rejected["id"]]["readiness_reason"] == "rejected_evidence"
    assert by_id[proposed["id"]]["readiness_reason"] == "decision_proposed"
    assert by_id[observed["id"]]["readiness_reason"] == "observed_evidence"
    assert [item["readiness_level"] for item in body["items"]] == [
        "blocked",
        "blocked",
        "review",
        "watch",
    ]


def test_verified_decisions_are_ready_and_hidden_by_default(client):
    decision = create_decision(client, "검증 완료 결정")
    review_decision_evidence(client, decision["id"], "verified", "readiness-verify-001")

    default = client.get("/api/v1/decisions/readiness").json()
    included = client.get("/api/v1/decisions/readiness?include_ready=true").json()

    assert default["summary"]["ready_decisions"] == 1
    assert default["items"] == []
    assert included["items"][0]["id"] == decision["id"]
    assert included["items"][0]["readiness_level"] == "ready"
    assert included["items"][0]["readiness_reason"] == "verified_evidence"
    assert included["items"][0]["evidence_counts"]["verified"] == 1


def test_review_deadlines_and_expiring_verified_decisions_are_prioritized(client):
    now = datetime.now(UTC)
    overdue = create_decision(
        client,
        "재검토 기한 경과",
        effective_at=(now - timedelta(days=30)).isoformat(),
        review_due_at=(now - timedelta(minutes=1)).isoformat(),
    )
    expiring = create_decision(
        client,
        "곧 만료되는 검증 결정",
        effective_at=(now - timedelta(days=1)).isoformat(),
        expires_at=(now + timedelta(days=7)).isoformat(),
    )
    review_decision_evidence(client, overdue["id"], "verified", "readiness-verify-002")
    review_decision_evidence(client, expiring["id"], "verified", "readiness-verify-003")

    body = client.get("/api/v1/decisions/readiness").json()
    by_id = {item["id"]: item for item in body["items"]}

    assert by_id[overdue["id"]]["readiness_level"] == "review"
    assert by_id[overdue["id"]]["readiness_reason"] == "review_overdue"
    assert "verified_evidence" in by_id[overdue["id"]]["signals"]
    assert by_id[expiring["id"]]["readiness_level"] == "watch"
    assert by_id[expiring["id"]]["readiness_reason"] == "expires_soon"


def test_closed_decisions_are_counted_but_hidden_by_default(client):
    decision = create_decision(client, "철회된 결정")
    transitioned = client.post(
        f"/api/v1/decisions/{decision['id']}/transition",
        json={"status": "revoked", "note": "운영 방침 변경"},
    )
    assert transitioned.status_code == 200

    default = client.get("/api/v1/decisions/readiness").json()
    included = client.get("/api/v1/decisions/readiness?include_closed=true").json()

    assert default["summary"]["closed_decisions"] == 1
    assert default["items"] == []
    assert included["items"][0]["readiness_level"] == "closed"
    assert included["items"][0]["readiness_reason"] == "decision_closed"


def test_decision_readiness_is_read_only_tenant_safe_and_limit_safe(client):
    first = create_decision(client, "첫 결정")
    second = create_decision(client, "둘째 결정")
    create_decision(client, "다른 회사 결정", tenant="other")
    before = client.get("/api/v1/audit-events?limit=100").json()

    body = client.get("/api/v1/decisions/readiness?limit=1").json()
    after = client.get("/api/v1/audit-events?limit=100").json()
    other = client.get(
        "/api/v1/decisions/readiness",
        headers={"X-Tenant-ID": "other"},
    ).json()

    assert after == before
    assert body["summary"]["total_decisions"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] in {first["id"], second["id"]}
    assert other["summary"]["total_decisions"] == 1
    assert len(other["items"]) == 1
