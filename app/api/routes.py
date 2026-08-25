from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.security import TenantContext, get_tenant_context
from app.db import get_session
from app.models import (
    Approval,
    ApprovalStatus,
    AuditEvent,
    Decision,
    KnowledgeItem,
    Memory,
    Task,
)
from app.schemas import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalRead,
    AuditEventRead,
    DecisionCreate,
    DecisionRead,
    DispatchResponse,
    KnowledgeCreate,
    KnowledgeRead,
    MemoryCreate,
    MemoryRead,
    TaskCreate,
    TaskDetail,
    TaskRead,
)
from app.services.audit import add_audit_event
from app.services.task_service import execute_task_with_new_session

router = APIRouter(prefix="/api/v1")


async def require_task(session: AsyncSession, task_id: str, tenant_id: str) -> Task:
    query = select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id)
    task = (await session.scalars(query)).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Task:
    if payload.idempotency_key:
        query = select(Task).where(
            Task.tenant_id == context.tenant_id,
            Task.idempotency_key == payload.idempotency_key,
        )
        existing = (await session.scalars(query)).first()
        if existing:
            return existing
    task = Task(tenant_id=context.tenant_id, **payload.model_dump())
    session.add(task)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=context.actor,
        action="task.created",
        resource_type="task",
        resource_id=task.id,
    )
    await session.commit()
    await session.refresh(task)
    return task


@router.get("/tasks", response_model=list[TaskRead])
async def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[Task]:
    query = (
        select(Task)
        .where(Task.tenant_id == context.tenant_id)
        .order_by(Task.created_at.desc())
        .limit(limit)
    )
    result = await session.scalars(query)
    return list(result)


@router.get("/tasks/{task_id}", response_model=TaskDetail)
async def get_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Task:
    query = (
        select(Task)
        .where(Task.id == task_id, Task.tenant_id == context.tenant_id)
        .options(selectinload(Task.runs))
    )
    task = (await session.scalars(query)).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/run", response_model=DispatchResponse, status_code=202)
async def run_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> DispatchResponse:
    task = await require_task(session, task_id, context.tenant_id)
    if task.status in {task.status.DISPATCHED, task.status.RUNNING}:
        raise HTTPException(status_code=409, detail="Task is already running")
    task.status = task.status.DISPATCHED
    await session.commit()
    if settings.task_execution_mode == "worker":
        from app.worker import execute_task_job

        execute_task_job.delay(task.id)
    else:
        background_tasks.add_task(execute_task_with_new_session, task.id, True, False)
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=context.actor,
        action="task.dispatched",
        resource_type="task",
        resource_id=task.id,
    )
    await session.commit()
    return DispatchResponse(
        task_id=task.id,
        status=task.status,
        execution_mode=settings.task_execution_mode,
    )


@router.post("/memories", response_model=MemoryRead, status_code=201)
async def create_memory(
    payload: MemoryCreate,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Memory:
    if payload.source_task_id:
        await require_task(session, payload.source_task_id, context.tenant_id)
    item = Memory(tenant_id=context.tenant_id, **payload.model_dump())
    session.add(item)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=context.actor,
        action="memory.created",
        resource_type="memory",
        resource_id=item.id,
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/memories", response_model=list[MemoryRead])
async def list_memories(
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[Memory]:
    query = (
        select(Memory)
        .where(Memory.tenant_id == context.tenant_id)
        .order_by(Memory.created_at.desc())
    )
    return list(await session.scalars(query))


@router.post("/decisions", response_model=DecisionRead, status_code=201)
async def create_decision(
    payload: DecisionCreate,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Decision:
    if payload.task_id:
        await require_task(session, payload.task_id, context.tenant_id)
    item = Decision(tenant_id=context.tenant_id, **payload.model_dump())
    session.add(item)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=context.actor,
        action="decision.created",
        resource_type="decision",
        resource_id=item.id,
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/decisions", response_model=list[DecisionRead])
async def list_decisions(
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[Decision]:
    query = (
        select(Decision)
        .where(Decision.tenant_id == context.tenant_id)
        .order_by(Decision.created_at.desc())
    )
    return list(await session.scalars(query))


@router.post("/knowledge", response_model=KnowledgeRead, status_code=201)
async def create_knowledge(
    payload: KnowledgeCreate,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> KnowledgeItem:
    if payload.task_id:
        await require_task(session, payload.task_id, context.tenant_id)
    item = KnowledgeItem(tenant_id=context.tenant_id, **payload.model_dump())
    session.add(item)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=context.actor,
        action="knowledge.created",
        resource_type="knowledge",
        resource_id=item.id,
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/knowledge", response_model=list[KnowledgeRead])
async def list_knowledge(
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[KnowledgeItem]:
    query = (
        select(KnowledgeItem)
        .where(KnowledgeItem.tenant_id == context.tenant_id)
        .order_by(KnowledgeItem.created_at.desc())
    )
    return list(await session.scalars(query))


@router.post("/approvals", response_model=ApprovalRead, status_code=201)
async def create_approval(
    payload: ApprovalCreate,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Approval:
    if payload.task_id:
        await require_task(session, payload.task_id, context.tenant_id)
    item = Approval(tenant_id=context.tenant_id, **payload.model_dump())
    session.add(item)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=context.actor,
        action="approval.requested",
        resource_type="approval",
        resource_id=item.id,
        details={"task_id": item.task_id, "risk": item.risk},
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/approvals", response_model=list[ApprovalRead])
async def list_approvals(
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[Approval]:
    query = (
        select(Approval)
        .where(Approval.tenant_id == context.tenant_id)
        .order_by(Approval.created_at.desc())
    )
    return list(await session.scalars(query))


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalRead)
async def decide_approval(
    approval_id: str,
    payload: ApprovalDecision,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Approval:
    query = select(Approval).where(
        Approval.id == approval_id, Approval.tenant_id == context.tenant_id
    )
    item = (await session.scalars(query)).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if item.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail="Approval has already been decided")
    item.status = ApprovalStatus.APPROVED if payload.approved else ApprovalStatus.REJECTED
    item.decided_by = payload.decided_by
    item.decision_note = payload.note
    item.decided_at = datetime.now(UTC)
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=payload.decided_by,
        action=f"approval.{item.status.value}",
        resource_type="approval",
        resource_id=item.id,
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/audit-events", response_model=list[AuditEventRead])
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[AuditEvent]:
    query = (
        select(AuditEvent)
        .where(AuditEvent.tenant_id == context.tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    return list(await session.scalars(query))
