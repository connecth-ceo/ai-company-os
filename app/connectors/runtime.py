import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from app.connectors.contracts import ConnectorPayloadError, validate_connector_payload
from app.core.integrity import canonical_json_bytes, json_sha256

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ConnectorOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class ConnectorRuntimeError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class ConnectorInvocation:
    attempt_id: str
    tenant_id: str
    connector_key: str
    action_type: str
    payload_hash: str
    payload_json: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.attempt_id,
                self.tenant_id,
                self.connector_key,
                self.action_type,
            )
        ):
            raise ConnectorRuntimeError(
                "connector_invocation_invalid",
                "Connector invocation identifiers must contain visible text",
            )
        if not _SHA256_PATTERN.fullmatch(self.payload_hash):
            raise ConnectorRuntimeError(
                "connector_invocation_invalid",
                "Connector payload hash must be lowercase SHA-256 hex",
            )
        try:
            payload = json.loads(self.payload_json)
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise ConnectorRuntimeError(
                "connector_invocation_invalid",
                "Connector payload must be valid UTF-8 JSON",
            ) from exc
        if not isinstance(payload, dict) or canonical_json_bytes(payload) != self.payload_json:
            raise ConnectorRuntimeError(
                "connector_invocation_invalid",
                "Connector payload must use canonical JSON object encoding",
            )
        if json_sha256(payload) != self.payload_hash:
            raise ConnectorRuntimeError(
                "connector_payload_hash_mismatch",
                "Connector payload does not match the approved execution hash",
            )
        try:
            validate_connector_payload(self.action_type, payload)
        except ConnectorPayloadError as exc:
            raise ConnectorRuntimeError(exc.code, exc.detail) from exc


@dataclass(frozen=True, slots=True)
class ConnectorResult:
    attempt_id: str
    outcome: ConnectorOutcome
    outcome_code: str
    observed_at: datetime
    provider_reference_hash: str | None = None
    response_hash: str | None = None

    def __post_init__(self) -> None:
        try:
            normalized_outcome = ConnectorOutcome(self.outcome)
        except ValueError as exc:
            raise ConnectorRuntimeError(
                "connector_result_invalid",
                "Connector outcome must be succeeded, failed, or uncertain",
            ) from exc
        object.__setattr__(self, "outcome", normalized_outcome)
        normalized_code = self.outcome_code.strip()
        if not normalized_code:
            raise ConnectorRuntimeError(
                "connector_result_invalid",
                "Connector outcome code must contain visible text",
            )
        object.__setattr__(self, "outcome_code", normalized_code)
        if self.observed_at.tzinfo is None:
            raise ConnectorRuntimeError(
                "connector_result_invalid",
                "Connector observation timestamp must include a timezone",
            )
        proof_pair = (self.provider_reference_hash, self.response_hash)
        if any(value is not None and not _SHA256_PATTERN.fullmatch(value) for value in proof_pair):
            raise ConnectorRuntimeError(
                "connector_result_invalid",
                "Connector proof hashes must be lowercase SHA-256 hex",
            )
        if (self.provider_reference_hash is None) != (self.response_hash is None):
            raise ConnectorRuntimeError(
                "connector_result_invalid",
                "Connector proof hashes must be supplied together",
            )
        if self.outcome == ConnectorOutcome.SUCCEEDED and self.response_hash is None:
            raise ConnectorRuntimeError(
                "connector_result_invalid",
                "Successful connector execution requires provider proof hashes",
            )


@runtime_checkable
class ConnectorAdapter(Protocol):
    connector_key: str
    adapter_version: str
    action_types: tuple[str, ...]

    async def execute(self, invocation: ConnectorInvocation) -> ConnectorResult: ...


def build_connector_invocation(
    *,
    attempt_id: str,
    tenant_id: str,
    connector_key: str,
    action_type: str,
    payload: dict,
    expected_payload_hash: str,
) -> ConnectorInvocation:
    actual_hash = json_sha256(payload)
    if actual_hash != expected_payload_hash:
        raise ConnectorRuntimeError(
            "connector_payload_hash_mismatch",
            "Connector payload does not match the approved execution hash",
        )
    try:
        validate_connector_payload(action_type, payload)
    except ConnectorPayloadError as exc:
        raise ConnectorRuntimeError(exc.code, exc.detail) from exc
    return ConnectorInvocation(
        attempt_id=attempt_id,
        tenant_id=tenant_id,
        connector_key=connector_key,
        action_type=action_type,
        payload_hash=actual_hash,
        payload_json=canonical_json_bytes(payload),
    )


class ConnectorAdapterRegistry:
    def __init__(self, adapters: Iterable[ConnectorAdapter] = ()) -> None:
        registered: dict[str, ConnectorAdapter] = {}
        for adapter in adapters:
            if not isinstance(adapter, ConnectorAdapter):
                raise ConnectorRuntimeError(
                    "connector_adapter_invalid",
                    "Connector adapter does not implement the runtime port",
                )
            if adapter.connector_key in registered:
                raise ConnectorRuntimeError(
                    "connector_adapter_duplicate",
                    f"Connector adapter '{adapter.connector_key}' is registered twice",
                )
            if not adapter.adapter_version.strip() or not adapter.action_types:
                raise ConnectorRuntimeError(
                    "connector_adapter_invalid",
                    "Connector adapter version and action types are required",
                )
            registered[adapter.connector_key] = adapter
        self._adapters = registered

    def available(self, connector_key: str, action_type: str) -> bool:
        adapter = self._adapters.get(connector_key)
        return adapter is not None and action_type in adapter.action_types

    def require(self, connector_key: str, action_type: str) -> ConnectorAdapter:
        adapter = self._adapters.get(connector_key)
        if adapter is None:
            raise ConnectorRuntimeError(
                "connector_adapter_unavailable",
                f"Connector adapter '{connector_key}' is not installed",
            )
        if action_type not in adapter.action_types:
            raise ConnectorRuntimeError(
                "connector_adapter_action_not_allowed",
                f"Connector adapter '{connector_key}' cannot execute '{action_type}'",
            )
        return adapter

    async def execute(self, invocation: ConnectorInvocation) -> ConnectorResult:
        adapter = self.require(invocation.connector_key, invocation.action_type)
        try:
            result = await adapter.execute(invocation)
        except ConnectorRuntimeError:
            raise
        except Exception as exc:
            raise ConnectorRuntimeError(
                "connector_adapter_failed",
                "Connector adapter failed without a verified result",
            ) from exc
        if not isinstance(result, ConnectorResult):
            raise ConnectorRuntimeError(
                "connector_result_invalid",
                "Connector adapter returned an unsupported result type",
            )
        if result.attempt_id != invocation.attempt_id:
            raise ConnectorRuntimeError(
                "connector_result_attempt_mismatch",
                "Connector result does not belong to the requested execution attempt",
            )
        return result


EMPTY_CONNECTOR_ADAPTER_REGISTRY = ConnectorAdapterRegistry()


def get_connector_adapter_registry() -> ConnectorAdapterRegistry:
    """FastAPI dependency seam; production remains fail-closed until an adapter is installed."""

    return EMPTY_CONNECTOR_ADAPTER_REGISTRY
