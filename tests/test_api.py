def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_task_runs_end_to_end_in_mock_mode(client):
    created = client.post(
        "/api/v1/tasks",
        json={
            "title": "신제품 시장 진입 검토",
            "request": "한국 시장 진입을 위한 첫 30일 계획을 만들어줘.",
            "priority": 2,
        },
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    dispatched = client.post(f"/api/v1/tasks/{task_id}/run")
    assert dispatched.status_code == 202
    assert dispatched.json()["execution_mode"] == "inline"

    detail = client.get(f"/api/v1/tasks/{task_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "completed"
    assert "비서실장 보고" in body["result"]
    assert body["runs"][0]["verdict"] == "PASS"

    knowledge = client.get("/api/v1/knowledge")
    assert knowledge.status_code == 200
    assert knowledge.json()[0]["task_id"] == task_id


def test_persistent_company_records_and_approval_decision(client):
    memory = client.post(
        "/api/v1/memories",
        json={"category": "preference", "content": "보고서는 결론부터 작성한다."},
    )
    assert memory.status_code == 201

    decision = client.post(
        "/api/v1/decisions",
        json={
            "subject": "초기 인터페이스",
            "choice": "Telegram",
            "rationale": "모바일에서 즉시 승인하기 쉽다.",
        },
    )
    assert decision.status_code == 201

    approval = client.post(
        "/api/v1/approvals",
        json={
            "action": "고객에게 제안서 발송",
            "reason": "외부 커뮤니케이션이므로 대표 확인 필요",
            "risk": "high",
        },
    )
    assert approval.status_code == 201
    approval_id = approval.json()["id"]

    decided = client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        json={"approved": True, "decided_by": "CEO", "note": "발송 승인"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"


def test_saved_company_context_is_used_by_later_tasks(client):
    client.post(
        "/api/v1/memories",
        json={"category": "reporting", "content": "항상 결론과 다음 행동을 먼저 제시한다."},
    )
    client.post(
        "/api/v1/decisions",
        json={
            "subject": "주요 시장",
            "choice": "한국 시장 우선",
            "rationale": "초기 고객 접근성이 가장 높다.",
        },
    )

    task = client.post(
        "/api/v1/tasks",
        json={"title": "회사 맥락 확인", "request": "다음 실행 계획을 정리해줘."},
    ).json()
    client.post(f"/api/v1/tasks/{task['id']}/run")
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()

    assert detail["runs"][0]["artifacts"]["company_context_used"] is True
    assert "회사 맥락 반영" in detail["result"]


def test_high_impact_request_creates_pending_ceo_approval(client):
    task = client.post(
        "/api/v1/tasks",
        json={
            "title": "고객 발송",
            "request": "완성된 제안서를 고객에게 발송해줘.",
        },
    ).json()
    client.post(f"/api/v1/tasks/{task['id']}/run")

    approvals = client.get("/api/v1/approvals").json()
    matching = [item for item in approvals if item["task_id"] == task["id"]]
    assert len(matching) == 1
    assert matching[0]["status"] == "pending"
    assert matching[0]["risk"] == "medium"

    events = client.get("/api/v1/audit-events").json()
    assert any(event["action"] == "approval.requested" for event in events)
