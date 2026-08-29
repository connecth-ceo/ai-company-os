from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class ConnectorRisk(StrEnum):
    EXTERNAL_WRITE = "external_write"
    HIGH_IMPACT = "high_impact"


@dataclass(frozen=True, slots=True)
class ConnectorDescriptor:
    key: str
    version: str
    provider: str
    purpose: str
    action_types: tuple[str, ...]
    risk: ConnectorRisk
    side_effects: bool = True
    approval_required: bool = True
    ledger_preparation_available: bool = True
    ledger_claim_available: bool = True
    external_execution_available: bool = False


class ConnectorPolicyError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def default_connector_catalog() -> tuple[ConnectorDescriptor, ...]:
    """Return contract-only connector slots. None can call an external provider yet."""

    return (
        ConnectorDescriptor(
            key="email_gateway",
            version="v1",
            provider="contract_only",
            purpose="Prepare approved outbound email actions for a future provider adapter.",
            action_types=("email_send",),
            risk=ConnectorRisk.EXTERNAL_WRITE,
        ),
        ConnectorDescriptor(
            key="external_publish_gateway",
            version="v1",
            provider="contract_only",
            purpose="Prepare approved generic external publishing actions.",
            action_types=("external_publish",),
            risk=ConnectorRisk.EXTERNAL_WRITE,
        ),
        ConnectorDescriptor(
            key="smartstore_gateway",
            version="v1",
            provider="contract_only",
            purpose=(
                "Reserve Naver SmartStore catalog, price, campaign, and review action contracts."
            ),
            action_types=(
                "smartstore_campaign_start",
                "smartstore_price_update",
                "smartstore_product_publish",
                "smartstore_review_reply",
            ),
            risk=ConnectorRisk.HIGH_IMPACT,
        ),
    )


_CATALOG = {item.key: item for item in default_connector_catalog()}
if len(_CATALOG) != len(default_connector_catalog()):
    raise RuntimeError("Connector catalog keys must be unique")


def public_connector_catalog() -> tuple[ConnectorDescriptor, ...]:
    return tuple(_CATALOG[key] for key in sorted(_CATALOG))


def require_connector_action(
    connector_key: str,
    action_type: str,
    *,
    phase: Literal["prepare", "claim", "complete"],
) -> ConnectorDescriptor:
    descriptor = _CATALOG.get(connector_key)
    if descriptor is None:
        raise ConnectorPolicyError(
            "connector_not_registered",
            f"Connector '{connector_key}' is not registered",
        )
    if action_type not in descriptor.action_types:
        raise ConnectorPolicyError(
            "connector_action_not_allowed",
            f"Connector '{connector_key}' does not allow action type '{action_type}'",
        )
    if phase == "prepare" and not descriptor.ledger_preparation_available:
        raise ConnectorPolicyError(
            "connector_preparation_disabled",
            f"Connector '{connector_key}' does not allow ledger preparation",
        )
    if phase in {"claim", "complete"} and not descriptor.ledger_claim_available:
        raise ConnectorPolicyError(
            "connector_claim_disabled",
            f"Connector '{connector_key}' does not allow ledger claim or completion",
        )
    return descriptor


def require_external_execution(connector_key: str, action_type: str) -> ConnectorDescriptor:
    descriptor = require_connector_action(connector_key, action_type, phase="claim")
    if not descriptor.external_execution_available:
        raise ConnectorPolicyError(
            "connector_external_execution_disabled",
            f"Connector '{connector_key}' has no external execution adapter",
        )
    return descriptor
