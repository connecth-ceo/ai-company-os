import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
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


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewVerdict(StrEnum):
    PASS = "PASS"
    REWORK = "REWORK"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)

    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


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
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)


class Memory(Base, TimestampMixin):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    content: Mapped[str] = mapped_column(Text)
    source_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)


class Decision(Base, TimestampMixin):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    subject: Mapped[str] = mapped_column(String(240))
    choice: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(String(80), default="CEO")
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)


class KnowledgeItem(Base, TimestampMixin):
    __tablename__ = "knowledge_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(80), default="owner", index=True)
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)


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
