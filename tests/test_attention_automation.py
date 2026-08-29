from datetime import UTC, datetime, timedelta

from app.core.config import Settings, get_settings
from app.main import app


def commitment_payload(statement: str, *, overdue_hours: int) -> dict[str, str]:
    return {
        "statement": statement,
        "owner_id": "chief_of_staff",
        "due_at": (datetime.now(UTC) - timedelta(hours=overdue_hours)).isoformat(),
    }


def test_attention_automation_policy_is_fail_closed(client):
    response = client.get("/api/v1/attention/automation-policy")

    assert response.status_code == 200
    policy = response.json()
    assert policy["rule_version"] == "attention-auto-plan-v1"
    assert policy["enabled"] is False
    assert policy["automatic_kinds"] == [
        "overdue_commitment",
        "long_running_task",
        "task_failure",
    ]
    assert policy["automatic_levels"] == ["info", "watch", "action"]
    assert policy["manual_kinds"] == ["pending_approval", "decision_governance"]
    assert policy["manual_levels"] == ["decision", "critical"]
    assert policy["creates_task_execution"] is False
    assert policy["creates_external_action"] is False


def test_attention_automation_dry_run_has_no_side_effect(client):
    client.post(
        "/api/v1/commitments",
        json=commitment_payload("저위험 기한 초과", overdue_hours=2),
    )

    response = client.post("/api/v1/attention/automation/run", json={})

    assert response.status_code == 200
    result = response.json()
    assert result["enabled"] is False
    assert result["dry_run"] is True
    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["created"] == 0
    assert result["skipped"] == 0
    assert result["items"][0]["decision"] == "eligible"
    assert client.get("/api/v1/attention/follow-ups").json() == []
    assert client.get("/api/v1/tasks").json() == []
    assert client.get("/api/v1/attention?include_acknowledged=false").json()["total"] == 1


def test_attention_automation_live_run_is_blocked_while_disabled(client):
    client.post(
        "/api/v1/commitments",
        json=commitment_payload("비활성 차단", overdue_hours=2),
    )

    response = client.post(
        "/api/v1/attention/automation/run",
        json={"dry_run": False},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "attention_auto_plan_disabled"
    assert client.get("/api/v1/attention/follow-ups").json() == []


def test_attention_automation_only_plans_once_and_never_executes(client):
    client.post(
        "/api/v1/commitments",
        json=commitment_payload("자동 내부 계획", overdue_hours=2),
    )
    enabled = Settings(app_env="test", attention_auto_plan_enabled=True)
    app.dependency_overrides[get_settings] = lambda: enabled
    try:
        first = client.post(
            "/api/v1/attention/automation/run",
            json={"dry_run": False},
        )
        second = client.post(
            "/api/v1/attention/automation/run",
            json={"dry_run": False},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert first.status_code == 200
    result = first.json()
    assert result["created"] == 1
    assert result["items"][0]["decision"] == "created"
    task_id = result["items"][0]["task_id"]
    task = client.get(f"/api/v1/tasks/{task_id}").json()
    assert task["status"] == "queued"
    assert task["runs"] == []

    assert second.status_code == 200
    repeated = second.json()
    assert repeated["created"] == 0
    assert repeated["eligible"] == 0
    assert repeated["items"][0]["reason"] == "signal_already_planned"
    assert len(client.get("/api/v1/attention/follow-ups").json()) == 1


def test_attention_automation_leaves_elevated_and_decision_signals_manual(client):
    client.post(
        "/api/v1/commitments",
        json=commitment_payload("대표 판단 수준 기한 초과", overdue_hours=25),
    )
    client.post(
        "/api/v1/decisions",
        json={
            "subject": "자동화 제외 결정",
            "choice": "대표가 직접 검토한다.",
            "rationale": "자동계획 경계 검사",
        },
    )

    result = client.post("/api/v1/attention/automation/run", json={}).json()
    reasons = {item["kind"]: item["reason"] for item in result["items"]}

    assert reasons["overdue_commitment"] == "elevated_attention_level"
    assert reasons["decision_governance"] == "requires_ceo_decision"
    assert result["eligible"] == 0
    assert result["created"] == 0
    assert result["skipped"] == result["scanned"]
    assert client.get("/api/v1/attention/follow-ups").json() == []
