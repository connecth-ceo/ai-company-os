import pytest

from app.connectors.catalog import ConnectorPolicyError, require_external_execution


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
    for connector in connectors:
        assert connector["side_effects"] is True
        assert connector["approval_required"] is True
        assert connector["ledger_preparation_available"] is True
        assert connector["ledger_claim_available"] is True
        assert connector["external_execution_available"] is False
        assert "credential" not in connector
        assert "secret" not in connector
        assert "api_key" not in connector


def test_connector_external_execution_fails_closed_without_adapter():
    with pytest.raises(ConnectorPolicyError) as caught:
        require_external_execution("smartstore_gateway", "smartstore_product_publish")

    assert caught.value.code == "connector_external_execution_disabled"


def test_connector_catalog_has_no_write_endpoint(client):
    before = client.get("/api/v1/connector-catalog").json()

    unsupported = client.post(
        "/api/v1/connector-catalog",
        json={"key": "shadow_connector"},
    )

    assert unsupported.status_code in {404, 405}
    assert client.get("/api/v1/connector-catalog").json() == before
