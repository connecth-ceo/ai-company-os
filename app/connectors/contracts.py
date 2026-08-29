from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ConnectorPayloadError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class ConnectorPayload(BaseModel):
    """Versioned, secret-free payload passed from an approved intent to an adapter."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EmailSendPayload(ConnectorPayload):
    message_id: str = Field(min_length=1, max_length=100)
    recipients: list[str] = Field(min_length=1, max_length=50)
    subject: str = Field(min_length=1, max_length=200)
    body_asset_id: str = Field(min_length=1, max_length=120)

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, recipients: list[str]) -> list[str]:
        normalized = [recipient.strip().lower() for recipient in recipients]
        if len(normalized) != len(set(normalized)):
            raise ValueError("recipients must not contain duplicates")
        if any(
            not recipient
            or "@" not in recipient
            or recipient.startswith("@")
            or recipient.endswith("@")
            or any(character.isspace() for character in recipient)
            for recipient in normalized
        ):
            raise ValueError("recipients must contain valid email addresses")
        return normalized


class ExternalPublishPayload(ConnectorPayload):
    channel: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,79}$")
    draft_id: str = Field(min_length=1, max_length=120)
    audience: str = Field(min_length=1, max_length=120)


class SmartStoreProductPublishPayload(ConnectorPayload):
    merchant_product_id: str = Field(min_length=1, max_length=120)
    product_name: str = Field(min_length=1, max_length=100)
    category_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    sale_price_krw: int = Field(ge=100, le=1_000_000_000)
    stock_quantity: int = Field(ge=0, le=100_000_000)
    thumbnail_asset_ids: list[str] = Field(min_length=1, max_length=10)
    detail_page_asset_id: str = Field(min_length=1, max_length=120)
    legal_review_record_id: str = Field(min_length=1, max_length=120)
    shipping_policy_id: str = Field(min_length=1, max_length=120)

    @field_validator("thumbnail_asset_ids")
    @classmethod
    def validate_thumbnail_assets(cls, asset_ids: list[str]) -> list[str]:
        if any(not asset_id.strip() or len(asset_id.strip()) > 120 for asset_id in asset_ids):
            raise ValueError("thumbnail asset IDs must contain 1-120 visible characters")
        normalized = [asset_id.strip() for asset_id in asset_ids]
        if len(normalized) != len(set(normalized)):
            raise ValueError("thumbnail asset IDs must not contain duplicates")
        return normalized


class SmartStorePriceUpdatePayload(ConnectorPayload):
    product_id: str = Field(min_length=1, max_length=120)
    sale_price_krw: int = Field(ge=100, le=1_000_000_000)
    reason: str = Field(min_length=1, max_length=500)


class SmartStoreCampaignStartPayload(ConnectorPayload):
    campaign_id: str = Field(min_length=1, max_length=120)
    product_ids: list[str] = Field(min_length=1, max_length=100)
    channel: Literal["naver_search", "smartstore_display"]
    daily_budget_krw: int = Field(ge=1_000, le=1_000_000_000)
    starts_at: datetime
    ends_at: datetime

    @field_validator("product_ids")
    @classmethod
    def validate_product_ids(cls, product_ids: list[str]) -> list[str]:
        if any(
            not product_id.strip() or len(product_id.strip()) > 120 for product_id in product_ids
        ):
            raise ValueError("product IDs must contain 1-120 visible characters")
        normalized = [product_id.strip() for product_id in product_ids]
        if len(normalized) != len(set(normalized)):
            raise ValueError("product IDs must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def validate_window(self) -> "SmartStoreCampaignStartPayload":
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("campaign timestamps must include a timezone")
        if self.ends_at <= self.starts_at:
            raise ValueError("campaign end must be later than campaign start")
        return self


class SmartStoreReviewReplyPayload(ConnectorPayload):
    review_id: str = Field(min_length=1, max_length=120)
    reply_text: str = Field(min_length=1, max_length=1_000)
    moderation_record_id: str = Field(min_length=1, max_length=120)


@dataclass(frozen=True, slots=True)
class PayloadContractDescriptor:
    action_type: str
    schema_id: str
    version: str
    model: type[ConnectorPayload]


_CONTRACTS = {
    item.action_type: item
    for item in (
        PayloadContractDescriptor("email_send", "email.send", "v1", EmailSendPayload),
        PayloadContractDescriptor(
            "external_publish",
            "external.publish",
            "v1",
            ExternalPublishPayload,
        ),
        PayloadContractDescriptor(
            "smartstore_product_publish",
            "smartstore.product.publish",
            "v1",
            SmartStoreProductPublishPayload,
        ),
        PayloadContractDescriptor(
            "smartstore_price_update",
            "smartstore.price.update",
            "v1",
            SmartStorePriceUpdatePayload,
        ),
        PayloadContractDescriptor(
            "smartstore_campaign_start",
            "smartstore.campaign.start",
            "v1",
            SmartStoreCampaignStartPayload,
        ),
        PayloadContractDescriptor(
            "smartstore_review_reply",
            "smartstore.review.reply",
            "v1",
            SmartStoreReviewReplyPayload,
        ),
    )
}


def require_payload_contract(action_type: str) -> PayloadContractDescriptor:
    descriptor = _CONTRACTS.get(action_type)
    if descriptor is None:
        raise ConnectorPayloadError(
            "connector_payload_contract_missing",
            f"Action type '{action_type}' has no registered payload contract",
        )
    return descriptor


def payload_contracts_for(
    action_types: tuple[str, ...],
) -> tuple[PayloadContractDescriptor, ...]:
    return tuple(require_payload_contract(action_type) for action_type in action_types)


def validate_connector_payload(action_type: str, payload: dict[str, Any]) -> ConnectorPayload:
    descriptor = require_payload_contract(action_type)
    try:
        return descriptor.model.model_validate(payload)
    except ValidationError as exc:
        issues = "; ".join(
            f"{'.'.join(str(part) for part in issue['loc']) or 'payload'}: {issue['msg']}"
            for issue in exc.errors(include_url=False, include_context=False, include_input=False)
        )
        raise ConnectorPayloadError(
            "connector_payload_invalid",
            f"Payload does not satisfy {descriptor.schema_id}@{descriptor.version}: {issues}",
        ) from exc


def public_payload_schema(action_type: str) -> dict[str, Any]:
    descriptor = require_payload_contract(action_type)
    schema = descriptor.model.model_json_schema()
    return {
        "action_type": descriptor.action_type,
        "schema_id": descriptor.schema_id,
        "version": descriptor.version,
        "json_schema": schema,
    }
