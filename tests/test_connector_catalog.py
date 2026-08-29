import pytest

from app.connectors.catalog import ConnectorPolicyError, require_external_execution
from app.connectors.runtime import (
    ConnectorAdapterRegistry,
    ConnectorInvocation,
    ConnectorResult,
    get_connector_adapter_registry,
)
from app.main import app


class AvailablePublishAdapter:
    connector_key = "external_publish_gateway"
    adapter_version = "test-v1"
    action_types = ("external_publish",)

    async def execute(self, invocation: ConnectorInvocation) -> ConnectorResult:
        raise AssertionError("Catalog inspection must not execute an adapter")


def test_connector_catalog_is_read_only_secret_free_and_execution_disabled(client):
    response = client.get("/api/v1/connector-catalog")

    assert response.status_code == 200
    connectors = response.json()
    assert [item["key"] for item in connectors] == [
        "email_gateway",
        "external_publish_gateway",
        "smartstore_gateway",
    ]
    smartstore = next(item for item in connectors if item["key"] == "smartstore_gateway")
    assert smartstore["action_types"] == [
        "smartstore_campaign_start",
        "smartstore_price_update",
        "smartstore_product_publish",
        "smartstore_review_reply",
    ]
    assert [contract["schema_id"] for contract in smartstore["action_contracts"]] == [
        "smartstore.campaign.start",
        "smartstore.price.update",
        "smartstore.product.publish",
        "smartstore.review.reply",
    ]
    assert {contract["version"] for contract in smartstore["action_contracts"]} == {"v1"}
    for connector in connectors:
        assert connector["side_effects"] is True
        assert connector["approval_required"] is True
        assert connector["ledger_preparation_available"] is True
        assert connector["ledger_claim_available"] is True
        assert connector["external_execution_available"] is False
        assert "credential" not in connector
        assert "secret" not in connector
        assert "api_key" not in connector


def test_connector_payload_schema_is_read_only_and_forbids_unknown_fields(client):
    response = client.get(
        "/api/v1/connector-catalog/smartstore_gateway/actions/smartstore_product_publish/schema"
    )

    assert response.status_code == 200
    contract = response.json()
    assert contract["schema_id"] == "smartstore.product.publish"
    assert contract["version"] == "v1"
    schema = contract["json_schema"]
    assert schema["additionalProperties"] is False
    assert "legal_review_record_id" in schema["required"]
    assert "shipping_policy_id" in schema["required"]
    assert "credential" not in response.text.lower()
    assert "api_key" not in response.text.lower()

    mismatch = client.get(
        "/api/v1/connector-catalog/email_gateway/actions/smartstore_product_publish/schema"
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "connector_action_not_allowed"


def test_connector_external_execution_fails_closed_without_adapter():
    with pytest.raises(ConnectorPolicyError) as caught:
        require_external_execution("smartstore_gateway", "smartstore_product_publish")

    assert caught.value.code == "connector_external_execution_disabled"


def test_connector_catalog_derives_availability_from_installed_runtime_adapter(client):
    registry = ConnectorAdapterRegistry((AvailablePublishAdapter(),))
    app.dependency_overrides[get_connector_adapter_registry] = lambda: registry
    try:
        response = client.get("/api/v1/connector-catalog")
    finally:
        app.dependency_overrides.pop(get_connector_adapter_registry, None)

    assert response.status_code == 200
    catalog = {item["key"]: item for item in response.json()}
    assert catalog["external_publish_gateway"]["external_execution_available"] is True
    assert catalog["email_gateway"]["external_execution_available"] is False
    assert catalog["smartstore_gateway"]["external_execution_available"] is False
    enabled = require_external_execution(
        "external_publish_gateway",
        "external_publish",
        registry,
    )
    assert enabled.external_execution_available is True


def test_connector_catalog_has_no_write_endpoint(client):
    before = client.get("/api/v1/connector-catalog").json()

    unsupported = client.post(
        "/api/v1/connector-catalog",
        json={"key": "shadow_connector"},
    )

    assert unsupported.status_code in {404, 405}
    assert client.get("/api/v1/connector-catalog").json() == before
