from typing import Literal

from pydantic import BaseModel, Field

from app.models import ReviewVerdict


class ReviewerOutput(BaseModel):
    verdict: ReviewVerdict
    feedback: str = Field(description="Specific review feedback for the Chief of Staff")


class ApprovalRequest(BaseModel):
    action: str = Field(description="The exact external or high-impact action needing CEO approval")
    reason: str = Field(description="Why explicit CEO approval is required")
    risk: Literal["low", "medium", "high", "critical"] = "medium"


class ChiefOutput(BaseModel):
    final_report: str = Field(description="Executive-ready Korean report for the CEO")
    approval_requests: list[ApprovalRequest] = Field(
        default_factory=list,
        description=(
            "External, destructive, costly, publishing, deployment, or customer-facing actions "
            "that must wait for explicit CEO approval"
        ),
    )
