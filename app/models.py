import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid_str() -> str:
    return str(uuid.uuid4())


class TaskStatus(StrEnum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GoalStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    ACHIEVED = "achieved"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class ProjectStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewVerdict(StrEnum):
    PASS = "PASS"
    REWORK = "REWORK"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REVOKED = "revoked"


class DecisionScope(StrEnum):
    COMPANY = "company"
    PROJECT = "project"
    TASK = "task"
    DEPARTMENT = "department"


class ProvenanceSubjectType(StrEnum):
    KNOWLEDGE = "knowledge"
    DECISION = "decision"


class ProvenanceSourceType(StrEnum):
    URL = "url"
    TASK_RUN = "task_run"
    MANUAL = "manual"
    INHERITED = "inherited"


class ProvenanceVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    OBSERVED = "observed"
    VERIFIED = "verified"
    REJECTED = "rejected"


class CommitmentStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CommitmentOwnerType(StrEnum):
    PERSON = "person"
    AGENT = "agent"
    TEAM = "team"


class CommitmentSourceType(StrEnum):
    MANUAL = "manual"
    DECISION = "decision"
    TASK = "task"
    MEETING = "meeting"
    EXTERNAL = "external"


class AttentionLevel(StrEnum):
    INFO = "info"
    WATCH = "watch"
    ACTION = "action"
    DECISION = "decision"
    CRITICAL = "critical"


class AttentionKind(StrEnum):
    OVERDUE_COMMITMENT = "overdue_commitment"
    LONG_RUNNING_TASK = "long_running_task"
    TASK_FAILURE = "task_failure"
    PENDING_APPROVAL = "pending_approval"


class BriefingDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class ActionIntentStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_metric: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default=GoalStatus.ACTIVE, index=True)

    projects: Mapped[list["Project"]] = relationship(back_populates="goal")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default=ProjectStatus.ACTIVE, index=True)
    goal_id: Mapped[str | None] = mapped_column(
        ForeignKey("goals.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    tasks: Mapped[list["Task"]] = relationship(back_populates="project")
    goal: Mapped[Goal | None] = relationship(back_populates="projects")


class WorkflowDefinition(Base, TimestampMixin):
    __tablename__ = "workflow_definitions"
    __table_args__ = (UniqueConstraint("workflow_key", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workflow_key: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(default=True, index=True)

    runs: Mapped[list["WorkflowRun"]] = relationship(back_populates="definition")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key"),
        CheckConstraint(
            "parent_task_id IS NULL OR parent_task_id <> id",
            name="ck_task_not_self_parent",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(240))
    request: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.QUEUED)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="api")
    external_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    parent_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    runs: Mapped[list["TaskRun"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    project: Mapped[Project | None] = relationship(back_populates="tasks")
    parent: Mapped["Task | None"] = relationship(
        back_populates="children", remote_side="Task.id", foreign_keys=[parent_task_id]
    )
    children: Mapped[list["Task"]] = relationship(
        back_populates="parent", foreign_keys=[parent_task_id]
    )


class TaskRun(Base, TimestampMixin):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.RUNNING)
    agent: Mapped[str] = mapped_column(String(100), default="Chief of Staff")
    verdict: Mapped[ReviewVerdict | None] = mapped_column(Enum(ReviewVerdict), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifacts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[Task] = relationship(back_populates="runs")
    workflow_run: Mapped["WorkflowRun | None"] = relationship(
        back_populates="task_run", uselist=False
    )


class WorkflowRun(Base, TimestampMixin):
    __tablename__ = "workflow_runs"
    __table_args__ = (UniqueConstraint("task_run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    task_run_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), index=True
    )
    definition_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="RESTRICT"), index=True
    )
    workflow_key: Mapped[str] = mapped_column(String(100), index=True)
    workflow_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    definition_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    execution_plan: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    definition: Mapped[WorkflowDefinition] = relationship(back_populates="runs")
    task_run: Mapped[TaskRun] = relationship(back_populates="workflow_run")


class Delegation(Base, TimestampMixin):
    __tablename__ = "delegations"
    __table_args__ = (UniqueConstraint("child_task_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    parent_task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), index=True
    )
    child_task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), index=True
    )
    initiator: Mapped[str] = mapped_column(String(100))
    delegated_role: Mapped[str] = mapped_column(String(100), index=True)
    reason: Mapped[str] = mapped_column(Text)
    depth: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="created", index=True)
    token_budget: Mapped[int] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    cost_budget_usd: Mapped[float] = mapped_column(Numeric(10, 4))
    pricing_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    estimated_max_cost_usd: Mapped[float] = mapped_column(Numeric(14, 8), default=0)
    reserved_cost_usd: Mapped[float] = mapped_column(Numeric(14, 8), default=0)
    cost_reservation_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 8), nullable=True)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    approval_id: Mapped[str | None] = mapped_column(
        ForeignKey("approvals.id", ondelete="RESTRICT"), nullable=True, unique=True, index=True
    )
    task_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="RESTRICT"), nullable=True, unique=True, index=True
    )
    runtime_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AIMonthlyBudget(Base, TimestampMixin):
    __tablename__ = "ai_monthly_budgets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "period_start"),
        CheckConstraint("budget_usd >= 0", name="ck_ai_monthly_budget_nonnegative"),
        CheckConstraint("reserved_usd >= 0", name="ck_ai_monthly_reserved_nonnegative"),
        CheckConstraint(
            "estimated_spend_usd >= 0", name="ck_ai_monthly_estimated_spend_nonnegative"
        ),
        CheckConstraint(
            "uncertain_spend_usd >= 0", name="ck_ai_monthly_uncertain_spend_nonnegative"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    budget_usd: Mapped[float] = mapped_column(Numeric(14, 8))
    reserved_usd: Mapped[float] = mapped_column(Numeric(14, 8), default=0)
    estimated_spend_usd: Mapped[float] = mapped_column(Numeric(14, 8), default=0)
    uncertain_spend_usd: Mapped[float] = mapped_column(Numeric(14, 8), default=0)


class AICostLedgerEntry(Base):
    __tablename__ = "ai_cost_ledger"
    __table_args__ = (
        UniqueConstraint("delegation_id"),
        UniqueConstraint("task_run_id"),
        CheckConstraint("input_tokens >= 0", name="ck_ai_cost_input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="ck_ai_cost_output_tokens_nonnegative"),
        CheckConstraint("total_tokens >= 0", name="ck_ai_cost_total_tokens_nonnegative"),
        CheckConstraint("estimated_cost_usd >= 0", name="ck_ai_cost_estimate_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    delegation_id: Mapped[str] = mapped_column(
        ForeignKey("delegations.id", ondelete="RESTRICT"), index=True
    )
    task_run_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80), index=True)
    model: Mapped[str] = mapped_column(String(160), index=True)
    pricing_version: Mapped[str] = mapped_column(String(80))
    calculation_status: Mapped[str] = mapped_column(String(40), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    input_rate_per_million_usd: Mapped[float] = mapped_column(Numeric(14, 8))
    output_rate_per_million_usd: Mapped[float] = mapped_column(Numeric(14, 8))
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(14, 8))
    provider_billed_cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 8), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Memory(Base, TimestampMixin):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    content: Mapped[str] = mapped_column(Text)
    source_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)


class Decision(Base, TimestampMixin):
    __tablename__ = "decisions"
    __table_args__ = (
        UniqueConstraint(
            "supersedes_decision_id",
            name="uq_decisions_supersedes_decision_id",
        ),
        CheckConstraint(
            "supersedes_decision_id IS NULL OR supersedes_decision_id <> id",
            name="ck_decision_not_self_supersede",
        ),
        CheckConstraint(
            "status IN ('proposed', 'active', 'superseded', 'expired', 'revoked')",
            name="ck_decision_status",
        ),
        CheckConstraint(
            "scope IN ('company', 'project', 'task', 'department')",
            name="ck_decision_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    subject: Mapped[str] = mapped_column(String(240))
    choice: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(String(80), default="CEO")
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    status: Mapped[DecisionStatus] = mapped_column(
        String(40), default=DecisionStatus.ACTIVE, index=True
    )
    scope: Mapped[DecisionScope] = mapped_column(
        String(40), default=DecisionScope.COMPANY, index=True
    )
    applies_to: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("decisions.id", ondelete="RESTRICT"), nullable=True
    )
    superseded_decision: Mapped["Decision | None"] = relationship(
        remote_side="Decision.id",
        foreign_keys=[supersedes_decision_id],
    )


class Commitment(Base, TimestampMixin):
    __tablename__ = "commitments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'completed', 'cancelled')",
            name="ck_commitment_status",
        ),
        CheckConstraint(
            "owner_type IN ('person', 'agent', 'team')",
            name="ck_commitment_owner_type",
        ),
        CheckConstraint(
            "source_type IN ('manual', 'decision', 'task', 'meeting', 'external')",
            name="ck_commitment_source_type",
        ),
        CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR "
            "(status <> 'completed' AND completed_at IS NULL)",
            name="ck_commitment_completion_consistency",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    statement: Mapped[str] = mapped_column(Text)
    owner_type: Mapped[CommitmentOwnerType] = mapped_column(String(40), index=True)
    owner_id: Mapped[str] = mapped_column(String(100), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[CommitmentStatus] = mapped_column(
        String(40), default=CommitmentStatus.OPEN, index=True
    )
    source_type: Mapped[CommitmentSourceType] = mapped_column(
        String(40), default=CommitmentSourceType.MANUAL, index=True
    )
    source_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provenance: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("decisions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    reminder_policy: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_overdue(self) -> bool:
        if CommitmentStatus(self.status) not in {
            CommitmentStatus.OPEN,
            CommitmentStatus.IN_PROGRESS,
        }:
            return False
        due_at = self.due_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)
        return due_at.astimezone(UTC) < datetime.now(UTC)


class KnowledgeItem(Base, TimestampMixin):
    __tablename__ = "knowledge_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)


class ProvenanceRecord(Base, TimestampMixin):
    __tablename__ = "provenance_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key"),
        CheckConstraint(
            "subject_type IN ('knowledge', 'decision')",
            name="ck_provenance_subject_type",
        ),
        CheckConstraint(
            "source_type IN ('url', 'task_run', 'manual', 'inherited')",
            name="ck_provenance_source_type",
        ),
        CheckConstraint(
            "verification_status IN ('unverified', 'observed', 'verified', 'rejected')",
            name="ck_provenance_verification_status",
        ),
        CheckConstraint(
            "(subject_type = 'knowledge' AND knowledge_item_id IS NOT NULL "
            "AND decision_id IS NULL) OR "
            "(subject_type = 'decision' AND decision_id IS NOT NULL "
            "AND knowledge_item_id IS NULL)",
            name="ck_provenance_subject_reference",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    subject_type: Mapped[ProvenanceSubjectType] = mapped_column(String(40), index=True)
    knowledge_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("decisions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    task_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("provenance_records.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_type: Mapped[ProvenanceSourceType] = mapped_column(String(40), index=True)
    source_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_label: Mapped[str] = mapped_column(String(240))
    claim_reference: Mapped[str | None] = mapped_column(String(240), nullable=True)
    produced_by_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    verification_status: Mapped[ProvenanceVerificationStatus] = mapped_column(
        String(40), default=ProvenanceVerificationStatus.UNVERIFIED, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    record_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    action: Mapped[str] = mapped_column(String(240))
    reason: Mapped[str] = mapped_column(Text)
    risk: Mapped[str] = mapped_column(String(40), default="medium")
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING
    )
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActionIntent(Base, TimestampMixin):
    __tablename__ = "action_intents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key"),
        CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected', 'expired')",
            name="ck_action_intent_status",
        ),
        CheckConstraint(
            "execution_scope = 'single_use'",
            name="ck_action_intent_single_use_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approvals.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action_type: Mapped[str] = mapped_column(String(80), index=True)
    summary: Mapped[str] = mapped_column(String(240))
    reason: Mapped[str] = mapped_column(Text)
    risk: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    execution_scope: Mapped[str] = mapped_column(String(40), default="single_use")
    status: Mapped[ActionIntentStatus] = mapped_column(
        String(40), default=ActionIntentStatus.PROPOSED, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BriefingDelivery(Base, TimestampMixin):
    __tablename__ = "briefing_deliveries"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_briefing_deliveries_dedupe_key"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'uncertain')",
            name="ck_briefing_delivery_status",
        ),
        CheckConstraint(
            "(status = 'sent' AND sent_at IS NOT NULL) OR (status <> 'sent' AND sent_at IS NULL)",
            name="ck_briefing_delivery_sent_consistency",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    briefing_date: Mapped[date] = mapped_column(Date, index=True)
    channel: Mapped[str] = mapped_column(String(40), default="telegram", index=True)
    destination: Mapped[str] = mapped_column(String(120))
    dedupe_key: Mapped[str] = mapped_column(String(240), unique=True)
    status: Mapped[BriefingDeliveryStatus] = mapped_column(
        String(40), default=BriefingDeliveryStatus.PENDING, index=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
