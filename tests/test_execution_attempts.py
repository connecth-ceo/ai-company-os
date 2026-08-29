import asyncio
from datetime import UTC, datetime, timedelta

from app.db import SessionLocal
from app.models import ActionIntent


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
        "connector_key": "smartstore_connector",
        "idempotency_key": key,
        "timeout_seconds": 45,
    }


def test_execution_attempt_requires_approved_intent(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()

    response = client.post(
        f"/api/v1/action-intents/{intent['id']}/execution-attempts",
        json=preparation_payload(intent),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "intent_not_approved"
    assert client.get("/api/v1/execution-attempts").json() == []


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
    assert attempt["connector_key"] == "smartstore_connector"
    assert attempt["claimed_at"] is None
    assert attempt["deadline_at"] is None
    assert client.get(f"/api/v1/action-intents/{intent['id']}").json()["status"] == "approved"

    events = client.get("/api/v1/audit-events").json()
    prepared = next(item for item in events if item["action"] == "execution_attempt.prepared")
    assert prepared["details"]["payload_hash"] == intent["payload_hash"]
    assert prepared["details"]["external_call_started"] is False


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
