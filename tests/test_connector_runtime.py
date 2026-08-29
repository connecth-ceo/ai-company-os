from datetime import UTC, datetime

import pytest

from app.connectors.runtime import (
    EMPTY_CONNECTOR_ADAPTER_REGISTRY,
    ConnectorAdapterRegistry,
    ConnectorInvocation,
    ConnectorOutcome,
    ConnectorResult,
    ConnectorRuntimeError,
    build_connector_invocation,
)
from app.core.integrity import json_sha256


def publish_payload() -> dict:
    return {
        "channel": "company_blog",
        "draft_id": "draft-runtime-001",
        "audience": "customers",
    }


def invocation() -> ConnectorInvocation:
    payload = publish_payload()
    return build_connector_invocation(
        attempt_id="attempt-runtime-001",
        tenant_id="owner",
        connector_key="external_publish_gateway",
        action_type="external_publish",
        payload=payload,
        expected_payload_hash=json_sha256(payload),
    )


class FakePublishAdapter:
    connector_key = "external_publish_gateway"
    adapter_version = "test-v1"
    action_types = ("external_publish",)

    async def execute(self, request: ConnectorInvocation) -> ConnectorResult:
        return ConnectorResult(
            attempt_id=request.attempt_id,
            outcome=ConnectorOutcome.SUCCEEDED,
            outcome_code="fake_provider_confirmed",
            observed_at=datetime.now(UTC),
            provider_reference_hash="a" * 64,
            response_hash="b" * 64,
        )


@pytest.mark.asyncio
async def test_provider_neutral_adapter_port_returns_hash_only_result():
    registry = ConnectorAdapterRegistry((FakePublishAdapter(),))

    result = await registry.execute(invocation())

    assert result.outcome == ConnectorOutcome.SUCCEEDED
    assert result.provider_reference_hash == "a" * 64
    assert result.response_hash == "b" * 64
    assert registry.available("external_publish_gateway", "external_publish") is True
    assert "payload_json" not in repr(invocation())


def test_invocation_revalidates_approved_payload_hash_and_contract():
    payload = publish_payload()
    with pytest.raises(ConnectorRuntimeError) as changed:
        build_connector_invocation(
            attempt_id="attempt-runtime-001",
            tenant_id="owner",
            connector_key="external_publish_gateway",
            action_type="external_publish",
            payload={**payload, "audience": "different"},
            expected_payload_hash=json_sha256(payload),
        )
    with pytest.raises(ConnectorRuntimeError) as secret_field:
        build_connector_invocation(
            attempt_id="attempt-runtime-001",
            tenant_id="owner",
            connector_key="external_publish_gateway",
            action_type="external_publish",
            payload={**payload, "api_key": "must-not-cross-runtime-port"},
            expected_payload_hash=json_sha256(
                {**payload, "api_key": "must-not-cross-runtime-port"}
            ),
        )

    assert changed.value.code == "connector_payload_hash_mismatch"
    assert secret_field.value.code == "connector_payload_invalid"
    assert "must-not-cross-runtime-port" not in secret_field.value.detail


def test_success_result_requires_complete_sha256_proof_pair():
    with pytest.raises(ConnectorRuntimeError) as missing:
        ConnectorResult(
            attempt_id="attempt-runtime-001",
            outcome=ConnectorOutcome.SUCCEEDED,
            outcome_code="provider_confirmed",
            observed_at=datetime.now(UTC),
        )
    with pytest.raises(ConnectorRuntimeError) as partial:
        ConnectorResult(
            attempt_id="attempt-runtime-001",
            outcome=ConnectorOutcome.FAILED,
            outcome_code="provider_rejected",
            observed_at=datetime.now(UTC),
            response_hash="b" * 64,
        )

    assert missing.value.code == "connector_result_invalid"
    assert partial.value.code == "connector_result_invalid"


@pytest.mark.asyncio
async def test_registry_fails_closed_without_adapter_or_with_cross_attempt_result():
    with pytest.raises(ConnectorRuntimeError) as unavailable:
        await EMPTY_CONNECTOR_ADAPTER_REGISTRY.execute(invocation())

    class WrongAttemptAdapter(FakePublishAdapter):
        async def execute(self, request: ConnectorInvocation) -> ConnectorResult:
            result = await super().execute(request)
            return ConnectorResult(
                attempt_id="another-attempt",
                outcome=result.outcome,
                outcome_code=result.outcome_code,
                observed_at=result.observed_at,
                provider_reference_hash=result.provider_reference_hash,
                response_hash=result.response_hash,
            )

    registry = ConnectorAdapterRegistry((WrongAttemptAdapter(),))
    with pytest.raises(ConnectorRuntimeError) as mismatch:
        await registry.execute(invocation())

    assert unavailable.value.code == "connector_adapter_unavailable"
    assert mismatch.value.code == "connector_result_attempt_mismatch"


def test_registry_rejects_duplicate_adapter_keys():
    with pytest.raises(ConnectorRuntimeError) as duplicate:
        ConnectorAdapterRegistry((FakePublishAdapter(), FakePublishAdapter()))

    assert duplicate.value.code == "connector_adapter_duplicate"
