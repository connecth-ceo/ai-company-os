from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ApprovalStatus, ReviewVerdict, TaskStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    request: str = Field(min_length=1)
    priority: int = Field(default=3, ge=1, le=5)
    idempotency_key: str | None = Field(default=None, max_length=100)


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
    created_at: datetime
    updated_at: datetime


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


class TaskDetail(TaskRead):
    runs: list[TaskRunRead] = []


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
