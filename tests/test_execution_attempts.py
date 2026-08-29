import asyncio
from datetime import UTC, datetime, timedelta

from app.core.config import Settings, get_settings
from app.db import SessionLocal
from app.main import app
from app.models import ActionIntent, ExecutionAttempt


def action_payload(*, key: str = "execution-ledger-intent-001") -> dict:
    return {
        "action_type": "external_publish",
        "summary": "승인된 공지 게시 준비",
        "reason": "외부 게시 전 불변 실행 원장 검사",
        "risk": "high",
        "payload": {
            "channel": "company_blog",
            "draft_id": "draft-ledger-001",
            "audience": "customers",
        },
        "expires_in_minutes": 60,
        "idempotency_key": key,
    }


def approve(client, intent: dict) -> None:
    response = client.post(
        f"/api/v1/approvals/{intent['approval_id']}/decide",
        json={"approved": True, "decided_by": "CEO", "note": "실행 대상 승인"},
    )
    assert response.status_code == 200


def preparation_payload(intent: dict, *, key: str = "execution-attempt-001") -> dict:
    return {
        "expected_payload_hash": intent["payload_hash"],
        "connector_key": "external_publish_gateway",
        "idempotency_key": key,
        "timeout_seconds": 45,
    }


def create_claimed_attempt(client) -> tuple[dict, dict]:
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()
    approve(client, intent)
    attempt = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent),
    ).json()
    claimed = client.post(
        f"/api/v1/execution-attempts/{attempt['id']}/claim",
        json={
            "expected_payload_hash": intent["payload_hash"],
            "claimed_by": "connector_gateway",
        },
    ).json()
    return intent, claimed


def test_execution_attempt_requires_approved_intent(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()

    response = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "intent_not_approved"
    assert client.get("/api/v1/execution-attempts").json() == []


def test_execution_attempt_rejects_unknown_or_mismatched_connector(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()
    approve(client, intent)

    unknown = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json={**preparation_payload(intent), "connector_key": "unknown_gateway"},
    )
    mismatch = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json={**preparation_payload(intent), "connector_key": "email_gateway"},
    )

    assert unknown.status_code == 409
    assert unknown.json()["detail"]["code"] == "connector_not_registered"
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "connector_action_not_allowed"
    assert client.get("/api/v1/execution-attempts").json() == []


def test_execution_attempt_rejects_payload_outside_versioned_contract(client):
    invalid = action_payload(key="execution-ledger-invalid-contract-001")
    invalid["payload"] = {
        "channel": "company_blog",
        "draft_id": "draft-ledger-001",
        "unexpected_destination": "unapproved-field",
    }
    intent = client.post("/api/v1/action-intents", json=invalid).json()
    approve(client, intent)

    response = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent, key="execution-attempt-invalid-contract-001"),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "connector_payload_invalid"
    assert "unapproved-field" not in response.text
    assert client.get("/api/v1/execution-attempts").json() == []


def test_smartstore_contract_can_prepare_ledger_but_cannot_execute_external_api(client):
    intent = client.post(
        "/api/v1/action-intents",
        json={
            "action_type": "smartstore_product_publish",
            "summary": "검토 완료 상품 게시 준비",
            "reason": "법률 검토와 자산 참조가 완료된 상품만 원장에 준비",
            "risk": "critical",
            "payload": {
                "merchant_product_id": "merchant-product-001",
                "product_name": "자동화 검증 상품",
                "category_id": "cat-500001",
                "sale_price_krw": 39_900,
                "stock_quantity": 120,
                "thumbnail_asset_ids": ["asset-thumb-001", "asset-thumb-002"],
                "detail_page_asset_id": "asset-detail-001",
                "legal_review_record_id": "legal-review-001",
                "shipping_policy_id": "shipping-policy-001",
            },
            "expires_in_minutes": 60,
            "idempotency_key": "smartstore-product-publish-intent-001",
        },
    ).json()
    approve(client, intent)

    prepared = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json={
            "expected_payload_hash": intent["payload_hash"],
            "connector_key": "smartstore_gateway",
            "idempotency_key": "smartstore-product-publish-attempt-001",
            "timeout_seconds": 45,
        },
    )

    assert prepared.status_code == 201
    assert prepared.json()["status"] == "prepared"
    catalog = client.get("/api/v1/connector-catalog").json()
    smartstore = next(item for item in catalog if item["key"] == "smartstore_gateway")
    assert smartstore["external_execution_available"] is False


def test_execution_attempt_prepare_is_immutable_idempotent_and_side_effect_free(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()
    approve(client, intent)
    payload = preparation_payload(intent)

    first = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=payload,
    )
    repeated = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=payload,
    )

    assert first.status_code == 201
    attempt = first.json()
    assert repeated.status_code == 201
    assert repeated.json()["id"] == attempt["id"]
    assert attempt["status"] == "prepared"
    assert attempt["payload_hash"] == intent["payload_hash"]
    assert attempt["action_type"] == intent["action_type"]
    assert attempt["connector_key"] == "external_publish_gateway"
    assert attempt["claimed_at"] is None
    assert attempt["deadline_at"] is None
    assert client.get(f"/api/v1/action-intents/{intent['id']}").json()["status"] == "approved"

    events = client.get("/api/v1/audit-events").json()
    prepared = next(item for item in events if item["action"] == "execution_attempt.prepared")
    assert prepared["details"]["payload_hash"] == intent["payload_hash"]
    assert prepared["details"]["external_call_started"] is False


def test_execution_preflight_is_read_only_and_reports_adapter_blocker(client):
    intent = client.post(
        "/api/v1/action-intents",
        json=action_payload(key="execution-preflight-intent-001"),
    ).json()
    approve(client, intent)
    attempt = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent, key="execution-preflight-attempt-001"),
    ).json()
    events_before = client.get("/api/v1/audit-events").json()

    response = client.get(f"/api/v1/execution-attempts/{attempt['id']}/preflight")

    assert response.status_code == 200
    report = response.json()
    assert report["schema_id"] == "external.publish"
    assert report["schema_version"] == "v1"
    assert report["status"] == "prepared"
    assert report["payload_hash"] == intent["payload_hash"]
    assert report["payload_valid"] is True
    assert report["approval_valid"] is True
    assert report["external_execution_available"] is False
    assert report["executable"] is False
    assert report["blockers"] == ["external_adapter_unavailable"]
    assert client.get(f"/api/v1/action-intents/{intent['id']}").json()["status"] == "approved"
    assert client.get("/api/v1/audit-events").json() == events_before


def test_execution_preflight_detects_tampering_without_disclosing_payload(client):
    intent = client.post(
        "/api/v1/action-intents",
        json=action_payload(key="execution-preflight-tamper-intent-001"),
    ).json()
    approve(client, intent)
    attempt = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent, key="execution-preflight-tamper-attempt-001"),
    ).json()

    async def tamper() -> None:
        async with SessionLocal() as session:
            stored = await session.get(ActionIntent, intent["id"])
            assert stored is not None
            stored.payload = {
                "channel": "company_blog",
                "draft_id": "draft-ledger-001",
                "injected_destination": "do-not-disclose",
            }
            await session.commit()

    asyncio.run(tamper())
    response = client.get(f"/api/v1/execution-attempts/{attempt['id']}/preflight")

    assert response.status_code == 200
    report = response.json()
    assert report["payload_valid"] is False
    assert "payload_integrity_failed" in report["blockers"]
    assert "connector_payload_invalid" in report["blockers"]
    assert "do-not-disclose" not in response.text


def test_execution_preflight_is_tenant_isolated(client):
    intent = client.post(
        "/api/v1/action-intents",
        json=action_payload(key="execution-preflight-tenant-intent-001"),
    ).json()
    approve(client, intent)
    attempt = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent, key="execution-preflight-tenant-attempt-001"),
    ).json()

    response = client.get(
        f"/api/v1/execution-attempts/{attempt['id']}/preflight",
        headers={"X-Tenant-ID": "other"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "attempt_not_found"


def test_execution_attempt_claim_atomically_consumes_single_use_intent(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()
    approve(client, intent)
    attempt = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent),
    ).json()
    claim = {
        "expected_payload_hash": intent["payload_hash"],
        "claimed_by": "connector_gateway",
    }

    first = client.post(f"/api/v1/execution-attempts/{attempt['id']}/claim", json=claim)
    repeated = client.post(f"/api/v1/execution-attempts/{attempt['id']}/claim", json=claim)
    competing = client.post(
        f"/api/v1/execution-attempts/{attempt['id']}/claim",
        json={**claim, "claimed_by": "other_executor"},
    )

    assert first.status_code == 200
    claimed = first.json()
    assert claimed["status"] == "claimed"
    assert claimed["claimed_by"] == "connector_gateway"
    assert claimed["claimed_at"] is not None
    assert claimed["deadline_at"] is not None
    assert repeated.status_code == 200
    assert repeated.json()["id"] == claimed["id"]
    assert competing.status_code == 409
    assert competing.json()["detail"]["code"] == "attempt_already_claimed"
    assert client.get(f"/api/v1/action-intents/{intent['id']}").json()["status"] == "consumed"

    duplicate = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent, key="execution-attempt-002"),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "intent_already_consumed"
    events = client.get("/api/v1/audit-events").json()
    claimed_event = next(item for item in events if item["action"] == "execution_attempt.claimed")
    assert claimed_event["details"]["external_call_started"] is False


def test_execution_attempt_rechecks_hash_and_tenant(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()
    approve(client, intent)

    mismatch = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json={**preparation_payload(intent), "expected_payload_hash": "0" * 64},
    )
    other_tenant = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        headers={"X-Tenant-ID": "other"},
        json=preparation_payload(intent),
    )

    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "payload_hash_mismatch"
    assert other_tenant.status_code == 404
    assert other_tenant.json()["detail"]["code"] == "intent_not_found"
    assert client.get("/api/v1/execution-attempts", headers={"X-Tenant-ID": "other"}).json() == []


def test_execution_attempt_expiry_is_persisted_fail_closed(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()
    approve(client, intent)

    async def expire() -> None:
        async with SessionLocal() as session:
            stored = await session.get(ActionIntent, intent["id"])
            assert stored is not None
            stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()

    asyncio.run(expire())
    response = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "intent_expired"
    assert client.get(f"/api/v1/action-intents/{intent['id']}").json()["status"] == "expired"
    assert client.get("/api/v1/execution-attempts").json() == []


def test_execution_attempt_completion_is_terminal_and_idempotent(client):
    intent, attempt = create_claimed_attempt(client)
    payload = {
        "expected_payload_hash": intent["payload_hash"],
        "outcome": "succeeded",
        "outcome_code": "provider_confirmed",
        "completed_by": "connector_gateway",
    }

    first = client.post(
        f"/api/v1/execution-attempts/{attempt['id']}/complete",
        json=payload,
    )
    repeated = client.post(
        f"/api/v1/execution-attempts/{attempt['id']}/complete",
        json=payload,
    )
    conflicting = client.post(
        f"/api/v1/execution-attempts/{attempt['id']}/complete",
        json={**payload, "outcome": "failed", "outcome_code": "provider_rejected"},
    )

    assert first.status_code == 200
    completed = first.json()
    assert completed["status"] == "succeeded"
    assert completed["outcome_code"] == "provider_confirmed"
    assert completed["completed_at"] is not None
    assert repeated.status_code == 200
    assert repeated.json()["id"] == completed["id"]
    assert conflicting.status_code == 409
    assert conflicting.json()["detail"]["code"] == "attempt_already_completed"
    events = client.get("/api/v1/audit-events").json()
    succeeded = next(item for item in events if item["action"] == "execution_attempt.succeeded")
    assert succeeded["details"]["external_call_performed_by_this_service"] is False


def test_execution_attempt_cannot_complete_before_claim(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()
    approve(client, intent)
    attempt = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent),
    ).json()

    response = client.post(
        f"/api/v1/execution-attempts/{attempt['id']}/complete",
        json={
            "expected_payload_hash": intent["payload_hash"],
            "outcome": "failed",
            "outcome_code": "not_started",
            "completed_by": "connector_gateway",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "attempt_not_claimed"


def test_execution_attempt_recovery_is_dry_run_first_and_disabled_live(client):
    _, attempt = create_claimed_attempt(client)

    async def make_stale() -> None:
        async with SessionLocal() as session:
            stored = await session.get(ExecutionAttempt, attempt["id"])
            assert stored is not None
            stored.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(make_stale())
    dry_run = client.post("/api/v1/execution-attempts/recovery/run", json={})
    blocked = client.post(
        "/api/v1/execution-attempts/recovery/run",
        json={"dry_run": False},
    )

    assert dry_run.status_code == 200
    report = dry_run.json()
    assert report["enabled"] is False
    assert report["dry_run"] is True
    assert report["stale"] == 1
    assert report["transitioned"] == 0
    assert report["attempt_ids"] == [attempt["id"]]
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "execution_attempt_recovery_disabled"
    current = client.get("/api/v1/execution-attempts").json()[0]
    assert current["status"] == "claimed"


def test_execution_attempt_recovery_quarantines_without_retry(client):
    _, attempt = create_claimed_attempt(client)

    async def make_stale() -> None:
        async with SessionLocal() as session:
            stored = await session.get(ExecutionAttempt, attempt["id"])
            assert stored is not None
            stored.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(make_stale())
    enabled = Settings(app_env="test", execution_attempt_recovery_enabled=True)
    app.dependency_overrides[get_settings] = lambda: enabled
    try:
        response = client.post(
            "/api/v1/execution-attempts/recovery/run",
            json={"dry_run": False},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    report = response.json()
    assert report["transitioned"] == 1
    stored = client.get("/api/v1/execution-attempts").json()[0]
    assert stored["status"] == "uncertain"
    assert stored["outcome_code"] == "deadline_exceeded_without_confirmation"
    events = client.get("/api/v1/audit-events").json()
    uncertain = next(item for item in events if item["action"] == "execution_attempt.uncertain")
    assert uncertain["details"]["automatic_retry_started"] is False
