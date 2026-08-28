from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ApprovalStatus, ReviewVerdict, TaskStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


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
    choice: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    decided_by: str = "CEO"
    task_id: str | None = None


class DecisionRead(ORMModel):
    id: str
    tenant_id: str
    subject: str
    choice: str
    rationale: str
    decided_by: str
    task_id: str | None
    created_at: datetime


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
