import asyncio
from datetime import UTC, datetime, timedelta

from app.db import SessionLocal
from app.models import ActionIntent
from app.services.action_intents import payload_digest


def action_payload(**overrides) -> dict:
    payload = {
        "action_type": "external_publish",
        "summary": "검토된 공지 초안 게시 승인",
        "reason": "외부 채널 게시 전 대표 승인 필요",
        "risk": "high",
        "payload": {
            "channel": "company_blog",
            "draft_id": "draft-2026-001",
            "audience": "customers",
        },
        "expires_in_minutes": 60,
        "idempotency_key": "publish-draft-2026-001",
    }
    payload.update(overrides)
    return payload


def test_action_intent_creates_linked_approval_and_stable_hash(client):
    created = client.post("/api/v1/action-intents", json=action_payload())

    assert created.status_code == 201
    intent = created.json()
    assert intent["status"] == "proposed"
    assert intent["execution_scope"] == "single_use"
    assert intent["payload_hash"] == payload_digest(intent["payload"])
    assert len(intent["payload_hash"]) == 64

    approvals = client.get("/api/v1/approvals").json()
    approval = next(item for item in approvals if item["id"] == intent["approval_id"])
    assert approval["status"] == "pending"
    assert approval["action"] == intent["summary"]

    events = client.get("/api/v1/audit-events").json()
    proposed = next(item for item in events if item["action"] == "action_intent.proposed")
    assert proposed["resource_id"] == intent["id"]
    assert proposed["details"]["payload_hash"] == intent["payload_hash"]


def test_action_intent_approval_updates_state_but_never_executes(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()

    decided = client.post(
        f"/api/v1/approvals/{intent['approval_id']}/decide",
        json={"approved": True, "decided_by": "CEO", "note": "내용 승인"},
    )

    assert decided.status_code == 200
    stored = client.get(f"/api/v1/action-intents/{intent['id']}").json()
    assert stored["status"] == "approved"
    assert stored["decided_at"] is not None
    assert client.post(f"/api/v1/action-intents/{intent['id']}/execute").status_code in {
        404,
        405,
    }
    events = client.get("/api/v1/audit-events").json()
    approved = next(item for item in events if item["action"] == "action_intent.approved")
    assert approved["details"]["executed"] is False


def test_action_intent_idempotency_and_tenant_isolation(client):
    first = client.post("/api/v1/action-intents", json=action_payload()).json()
    repeated = client.post("/api/v1/action-intents", json=action_payload()).json()
    conflict_payload = action_payload(
        payload={"channel": "different", "draft_id": "draft-2026-001"}
    )
    conflict = client.post("/api/v1/action-intents", json=conflict_payload)

    assert repeated["id"] == first["id"]
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"
    assert (
        client.get(
            f"/api/v1/action-intents/{first['id']}", headers={"X-Tenant-ID": "other"}
        ).status_code
        == 404
    )
    assert client.get("/api/v1/action-intents", headers={"X-Tenant-ID": "other"}).json() == []


def test_action_intent_rejects_secret_fields_before_persistence(client):
    response = client.post(
        "/api/v1/action-intents",
        json=action_payload(payload={"channel": "email", "api_key": "must-not-store"}),
    )

    assert response.status_code == 422
    assert client.get("/api/v1/action-intents").json() == []
    assert client.get("/api/v1/approvals").json() == []


def test_expired_action_intent_fails_closed_and_rejects_approval(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()

    async def expire() -> None:
        async with SessionLocal() as session:
            item = await session.get(ActionIntent, intent["id"])
            assert item is not None
            item.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()

    asyncio.run(expire())
    decision = client.post(
        f"/api/v1/approvals/{intent['approval_id']}/decide",
        json={"approved": True, "decided_by": "CEO"},
    )

    assert decision.status_code == 409
    assert decision.json()["detail"]["code"] == "intent_expired"
    stored = client.get(f"/api/v1/action-intents/{intent['id']}").json()
    assert stored["status"] == "expired"
    approval = next(
        item
        for item in client.get("/api/v1/approvals").json()
        if item["id"] == intent["approval_id"]
    )
    assert approval["status"] == "rejected"
    assert approval["decided_by"] == "system"


def test_payload_tampering_blocks_approval_and_preserves_pending_state(client):
    intent = client.post("/api/v1/action-intents", json=action_payload()).json()

    async def tamper() -> None:
        async with SessionLocal() as session:
            item = await session.get(ActionIntent, intent["id"])
            assert item is not None
            item.payload = {"channel": "attacker", "draft_id": "changed"}
            await session.commit()

    asyncio.run(tamper())
    decision = client.post(
        f"/api/v1/approvals/{intent['approval_id']}/decide",
        json={"approved": True, "decided_by": "CEO"},
    )

    assert decision.status_code == 409
    assert decision.json()["detail"]["code"] == "payload_integrity_failed"
    approval = next(
        item
        for item in client.get("/api/v1/approvals").json()
        if item["id"] == intent["approval_id"]
    )
    assert approval["status"] == "pending"
