from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    ApprovalStatus,
    AttentionKind,
    AttentionLevel,
    BriefingDeliveryStatus,
    CommitmentOwnerType,
    CommitmentSourceType,
    CommitmentStatus,
    DecisionScope,
    DecisionStatus,
    ReviewVerdict,
    TaskStatus,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AttentionItemRead(BaseModel):
    id: str
    level: AttentionLevel
    kind: AttentionKind
    title: str
    summary: str
    recommendation: str
    resource_type: str
    resource_id: str
    project_id: str | None
    detected_at: datetime
    age_seconds: int
    evidence: dict[str, str | int | float | bool | None]


class AttentionQueueRead(BaseModel):
    rule_version: str
    generated_at: datetime
    total: int
    counts: dict[str, int]
    items: list[AttentionItemRead]


class BriefingDeliveryRead(ORMModel):
    id: str
    tenant_id: str
    briefing_date: date
    channel: str
    status: BriefingDeliveryStatus
    scheduled_for: datetime
    attempt_count: int
    last_attempt_at: datetime | None
    next_retry_at: datetime | None
    sent_at: datetime | None
    failure_code: str | None
    created_at: datetime
    updated_at: datetime


class BriefingScheduleRead(BaseModel):
    enabled: bool
    timezone: str
    daily_time: str
    quiet_hours: str
    catchup_hours: int
    max_attempts: int
    last_delivery: BriefingDeliveryRead | None


class ToolDescriptorRead(BaseModel):
    key: str
    purpose: str
    provider: str
    risk: str
    required_permissions: list[str]
    side_effects: bool
    approval_required: bool


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=50_000)
    status: str = Field(
        default="active",
        pattern="^(planned|active|on_hold|completed|archived)$",
    )


class ProjectRead(ORMModel):
    id: str
    tenant_id: str
    title: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    request: str = Field(min_length=1, max_length=50_000)
    priority: int = Field(default=3, ge=1, le=5)
    idempotency_key: str | None = Field(default=None, max_length=100)
    project_id: str | None = Field(default=None, max_length=36)
    parent_task_id: str | None = Field(default=None, max_length=36)


class TaskRead(ORMModel):
    id: str
    tenant_id: str
    title: str
    request: str
    priority: int
    status: TaskStatus
    result: str | None
    error: str | None
    source: str
    project_id: str | None
    parent_task_id: str | None
    created_at: datetime
    updated_at: datetime


class WorkflowDefinitionRead(ORMModel):
    id: str
    workflow_key: str
    version: str
    name: str
    description: str
    definition: dict
    checksum: str
    active: bool
    created_at: datetime
    updated_at: datetime


class WorkflowRunRead(ORMModel):
    id: str
    tenant_id: str
    task_id: str
    task_run_id: str
    workflow_key: str
    workflow_version: str
    status: str
    definition_snapshot: dict
    execution_plan: dict
    result_summary: dict
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class TaskRunRead(ORMModel):
    id: str
    task_id: str
    status: TaskStatus
    agent: str
    verdict: ReviewVerdict | None
    feedback: str | None
    artifacts: dict
    attempt: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration_ms: int | None
    started_at: datetime
    finished_at: datetime | None
    workflow_run: WorkflowRunRead | None = None


class TaskDetail(TaskRead):
    runs: list[TaskRunRead] = []


class DelegatedTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    request: str = Field(min_length=1, max_length=50_000)
    priority: int = Field(default=3, ge=1, le=5)
    delegated_role: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=100)
    reason: str = Field(min_length=1, max_length=2_000)
    token_budget: int = Field(default=10_000, ge=1)
    timeout_seconds: int = Field(default=600, ge=30)
    cost_budget_usd: float = Field(default=1.0, gt=0)


class DelegationRead(ORMModel):
    id: str
    tenant_id: str
    project_id: str | None
    parent_task_id: str
    child_task_id: str
    initiator: str
    delegated_role: str
    reason: str
    depth: int
    status: str
    token_budget: int
    timeout_seconds: int
    cost_budget_usd: float
    pricing_version: str | None
    estimated_max_cost_usd: float
    reserved_cost_usd: float
    cost_reservation_period_start: date | None
    actual_estimated_cost_usd: float | None
    policy_snapshot: dict
    approval_id: str | None
    task_run_id: str | None
    runtime_name: str | None
    provider: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration_ms: int | None
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    created_at: datetime


class AICostLedgerRead(ORMModel):
    id: str
    tenant_id: str
    delegation_id: str
    task_run_id: str
    provider: str
    model: str
    pricing_version: str
    calculation_status: str
    currency: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_rate_per_million_usd: float
    output_rate_per_million_usd: float
    estimated_cost_usd: float
    provider_billed_cost_usd: float | None
    occurred_at: datetime


class AICostSummaryRead(BaseModel):
    tenant_id: str
    provider: str
    period_start: date
    currency: str
    budget_usd: float
    reserved_usd: float
    estimated_spend_usd: float
    uncertain_spend_usd: float
    remaining_usd: float
    pricing_is_estimate: bool


class DelegationDispatchResponse(BaseModel):
    delegation_id: str
    child_task_id: str
    status: str
    execution_mode: str


class DelegationRecoveryRequest(BaseModel):
    dry_run: bool = True
    limit: int = Field(default=100, ge=1, le=500)


class DelegationRecoveryItem(BaseModel):
    delegation_id: str
    child_task_id: str
    previous_status: str
    action: str


class DelegationRecoveryResponse(BaseModel):
    dry_run: bool
    scanned: int
    stale: int
    reset_for_retry: int
    quarantined: int
    items: list[DelegationRecoveryItem]


class DispatchResponse(BaseModel):
    task_id: str
    status: TaskStatus
    execution_mode: str


class MemoryCreate(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1)
    source_task_id: str | None = None


class MemoryRead(ORMModel):
    id: str
    tenant_id: str
    category: str
    content: str
    source_task_id: str | None
    created_at: datetime


class DecisionCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=240)
    choice: str = Field(min_length=1, max_length=50_000)
    rationale: str = Field(min_length=1, max_length=50_000)
    decided_by: str = Field(default="CEO", min_length=1, max_length=80)
    task_id: str | None = Field(default=None, max_length=36)
    status: DecisionStatus = DecisionStatus.ACTIVE
    scope: DecisionScope = DecisionScope.COMPANY
    applies_to: dict[str, str] = Field(default_factory=dict)
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    review_due_at: datetime | None = None
    supersedes_decision_id: str | None = Field(default=None, max_length=36)


class DecisionRead(ORMModel):
    id: str
    tenant_id: str
    subject: str
    choice: str
    rationale: str
    decided_by: str
    task_id: str | None
    status: DecisionStatus
    scope: DecisionScope
    applies_to: dict[str, str]
    effective_at: datetime
    expires_at: datetime | None
    review_due_at: datetime | None
    supersedes_decision_id: str | None
    created_at: datetime
    updated_at: datetime


class DecisionTransition(BaseModel):
    status: DecisionStatus
    note: str | None = Field(default=None, max_length=2_000)


class CommitmentCreate(BaseModel):
    statement: str = Field(min_length=1, max_length=50_000)
    owner_type: CommitmentOwnerType = CommitmentOwnerType.PERSON
    owner_id: str = Field(min_length=1, max_length=100)
    due_at: datetime
    status: CommitmentStatus = CommitmentStatus.OPEN
    source_type: CommitmentSourceType = CommitmentSourceType.MANUAL
    source_id: str | None = Field(default=None, max_length=120)
    provenance: dict[str, str] = Field(default_factory=dict)
    project_id: str | None = Field(default=None, max_length=36)
    task_id: str | None = Field(default=None, max_length=36)
    decision_id: str | None = Field(default=None, max_length=36)
    reminder_policy: dict[str, str] = Field(default_factory=dict)


class CommitmentRead(ORMModel):
    id: str
    tenant_id: str
    statement: str
    owner_type: CommitmentOwnerType
    owner_id: str
    due_at: datetime
    status: CommitmentStatus
    source_type: CommitmentSourceType
    source_id: str | None
    provenance: dict[str, str]
    project_id: str | None
    task_id: str | None
    decision_id: str | None
    reminder_policy: dict[str, str]
    completed_at: datetime | None
    is_overdue: bool
    created_at: datetime
    updated_at: datetime


class CommitmentTransition(BaseModel):
    status: CommitmentStatus
    note: str | None = Field(default=None, max_length=2_000)


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1)
    source: str | None = None
    task_id: str | None = None


class KnowledgeRead(ORMModel):
    id: str
    tenant_id: str
    title: str
    content: str
    source: str | None
    task_id: str | None
    created_at: datetime


class ApprovalCreate(BaseModel):
    action: str = Field(min_length=1, max_length=240)
    reason: str = Field(min_length=1)
    risk: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    task_id: str | None = None


class ApprovalDecision(BaseModel):
    approved: bool
    decided_by: str = "CEO"
    note: str | None = None


class ApprovalRead(ORMModel):
    id: str
    tenant_id: str
    action: str
    reason: str
    risk: str
    status: ApprovalStatus
    task_id: str | None
    decided_by: str | None
    decision_note: str | None
    decided_at: datetime | None
    created_at: datetime


class AuditEventRead(ORMModel):
    id: str
    tenant_id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str | None
    details: dict
    created_at: datetime
