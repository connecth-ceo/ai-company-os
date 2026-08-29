from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.tool_gateway import public_tool_catalog
from app.connectors.catalog import (
    ConnectorPolicyError,
    public_connector_catalog,
    require_connector_action,
)
from app.connectors.contracts import payload_contracts_for, public_payload_schema
from app.core.config import Settings, get_settings
from app.core.security import TenantContext, get_tenant_context
from app.db import get_session
from app.models import (
    ActionIntent,
    AICostLedgerEntry,
    Approval,
    ApprovalStatus,
    AttentionAcknowledgement,
    AttentionKind,
    AttentionLevel,
    AuditEvent,
    BriefingDelivery,
    BriefingDeliveryStatus,
    Commitment,
    CommitmentStatus,
    Decision,
    DecisionScope,
    DecisionStatus,
    Delegation,
    ExecutionAttempt,
    Goal,
    KnowledgeItem,
    Memory,
    Project,
    ProvenanceRecord,
    ProvenanceReview,
    ProvenanceSubjectType,
    ProvenanceVerificationStatus,
    Task,
    TaskRun,
    WorkflowDefinition,
    WorkflowRun,
)
from app.schemas import (
    ActionIntentCreate,
    ActionIntentRead,
    AgentDirectoryEntryRead,
    AICostLedgerRead,
    AICostSummaryRead,
    ApprovalCreate,
    ApprovalDecision,
    ApprovalRead,
    AttentionAcknowledgementCreate,
    AttentionAcknowledgementRead,
    AttentionAutomationPolicyRead,
    AttentionAutomationRunRead,
    AttentionAutomationRunRequest,
    AttentionFollowUpCreate,
    AttentionFollowUpRead,
    AttentionQueueRead,
    AuditEventRead,
    BriefingDeliveryRead,
    BriefingScheduleRead,
    CommitmentCreate,
    CommitmentRead,
    CommitmentTransition,
    CompanyContextResourceType,
    CompanyContextSearchResponse,
    ConnectorActionContractRead,
    ConnectorDescriptorRead,
    DecisionCreate,
    DecisionFollowThroughRead,
    DecisionRead,
    DecisionReadinessRead,
    DecisionTransition,
    DelegatedTaskCreate,
    DelegationDispatchResponse,
    DelegationRead,
    DelegationRecoveryRequest,
    DelegationRecoveryResponse,
    DispatchResponse,
    ExecutionAttemptClaim,
    ExecutionAttemptComplete,
    ExecutionAttemptPrepare,
    ExecutionAttemptRead,
    ExecutionAttemptRecoveryRead,
    ExecutionAttemptRecoveryRunRequest,
    GoalCreate,
    GoalRead,
    GoalTransition,
    KnowledgeCreate,
    KnowledgeRead,
    MemoryCreate,
    MemoryRead,
    PortfolioHealthRead,
    ProjectCreate,
    ProjectRead,
    ProjectTransition,
    ProvenanceQualityRead,
    ProvenanceRead,
    ProvenanceReviewCreate,
    ProvenanceReviewRead,
    TaskCreate,
    TaskDetail,
    TaskRead,
    ToolDescriptorRead,
    WorkflowDefinitionRead,
    WorkflowRunRead,
)
from app.services import (
    action_intents,
    agent_directory,
    attention,
    attention_acknowledgements,
    attention_automation,
    attention_follow_ups,
    commitments,
    company_search,
    decision_follow_through,
    decision_memory,
    decision_readiness,
    execution_attempts,
    portfolio,
    portfolio_health,
    provenance_quality,
    provenance_reviews,
)
from app.services.ai_costs import (
    get_current_month_cost_summary,
    release_delegation_cost_reservation,
)
from app.services.audit import add_audit_event
from app.services.delegation import DelegationRejected, create_delegation
from app.services.delegation_execution import (
    DelegationExecutionRejected,
    dispatch_delegation,
    execute_delegation_with_new_session,
)
from app.services.delegation_recovery import recover_stale_delegations
from app.services.task_service import execute_task_with_new_session
from app.workflows.catalog import ensure_workflow_definitions

router = APIRouter(prefix="/api/v1")


@router.get("/agents", response_model=list[AgentDirectoryEntryRead])
async def list_agents(
    settings: Settings = Depends(get_settings),
    _: TenantContext = Depends(get_tenant_context),
) -> tuple[AgentDirectoryEntryRead, ...]:
    return agent_directory.list_public_agent_profiles(settings)


@router.get("/agents/{agent_key}", response_model=AgentDirectoryEntryRead)
async def get_agent(
    agent_key: str,
    settings: Settings = Depends(get_settings),
    _: TenantContext = Depends(get_tenant_context),
) -> AgentDirectoryEntryRead:
    profile = agent_directory.get_public_agent_profile(settings, agent_key)
    if profile is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return profile


@router.get("/context/search", response_model=CompanyContextSearchResponse)
async def search_company_context(
    q: str = Query(min_length=2, max_length=200),
    resource_types: list[CompanyContextResourceType] | None = Query(
        default=None,
        alias="type",
    ),
    effective_decisions_only: bool = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> CompanyContextSearchResponse:
    selected_types = set(resource_types or CompanyContextResourceType)
    return await company_search.search_company_context(
        session,
        tenant_id=context.tenant_id,
        query=q,
        resource_types=selected_types,
        effective_decisions_only=effective_decisions_only,
        limit=limit,
    )


def action_intent_rejection(error: action_intents.ActionIntentRejected) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": error.code, "message": error.detail})


@router.post("/action-intents", response_model=ActionIntentRead, status_code=201)
async def create_action_intent(
    payload: ActionIntentCreate,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> ActionIntent:
    if payload.task_id:
        await require_task(session, payload.task_id, context.tenant_id)
    try:
        item = await action_intents.create_action_intent(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            payload=payload,
        )
    except action_intents.ActionIntentRejected as exc:
        raise action_intent_rejection(exc) from exc
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/action-intents", response_model=list[ActionIntentRead])
async def list_action_intents(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[ActionIntent]:
    query = (
        select(ActionIntent)
        .where(ActionIntent.tenant_id == context.tenant_id)
        .order_by(ActionIntent.created_at.desc())
        .limit(limit)
    )
    return list(await session.scalars(query))


@router.get("/action-intents/{intent_id}", response_model=ActionIntentRead)
async def get_action_intent(
    intent_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> ActionIntent:
    item = await session.scalar(
        select(ActionIntent).where(
            ActionIntent.id == intent_id,
            ActionIntent.tenant_id == context.tenant_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Action intent not found")
    return item


def execution_attempt_rejection(
    error: execution_attempts.ExecutionAttemptRejected,
) -> HTTPException:
    status_code = 404 if error.code in {"intent_not_found", "attempt_not_found"} else 409
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.detail},
    )


@router.post(
    "/action-intents/{intent_id}/execution-attempts",
    response_model=ExecutionAttemptRead,
    status_code=201,
)
async def prepare_execution_attempt(
    intent_id: str,
    payload: ExecutionAttemptPrepare,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> ExecutionAttempt:
    try:
        attempt = await execution_attempts.prepare_execution_attempt(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            intent_id=intent_id,
            payload=payload,
        )
    except execution_attempts.ExecutionAttemptRejected as exc:
        if exc.code == "intent_expired":
            await session.commit()
        else:
            await session.rollback()
        raise execution_attempt_rejection(exc) from exc
    await session.commit()
    await session.refresh(attempt)
    return attempt


@router.get("/execution-attempts", response_model=list[ExecutionAttemptRead])
async def list_execution_attempts(
    action_intent_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[ExecutionAttempt]:
    conditions = [ExecutionAttempt.tenant_id == context.tenant_id]
    if action_intent_id is not None:
        conditions.append(ExecutionAttempt.action_intent_id == action_intent_id)
    query = (
        select(ExecutionAttempt)
        .where(*conditions)
        .order_by(ExecutionAttempt.created_at.desc())
        .limit(limit)
    )
    return list(await session.scalars(query))


@router.post(
    "/execution-attempts/{attempt_id}/claim",
    response_model=ExecutionAttemptRead,
)
async def claim_execution_attempt(
    attempt_id: str,
    payload: ExecutionAttemptClaim,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> ExecutionAttempt:
    try:
        attempt = await execution_attempts.claim_execution_attempt(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            attempt_id=attempt_id,
            payload=payload,
        )
    except execution_attempts.ExecutionAttemptRejected as exc:
        if exc.code == "intent_expired":
            await session.commit()
        else:
            await session.rollback()
        raise execution_attempt_rejection(exc) from exc
    await session.commit()
    await session.refresh(attempt)
    return attempt


@router.post(
    "/execution-attempts/{attempt_id}/complete",
    response_model=ExecutionAttemptRead,
)
async def complete_execution_attempt(
    attempt_id: str,
    payload: ExecutionAttemptComplete,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> ExecutionAttempt:
    try:
        attempt = await execution_attempts.complete_execution_attempt(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            attempt_id=attempt_id,
            payload=payload,
        )
    except execution_attempts.ExecutionAttemptRejected as exc:
        await session.rollback()
        raise execution_attempt_rejection(exc) from exc
    await session.commit()
    await session.refresh(attempt)
    return attempt


@router.post(
    "/execution-attempts/recovery/run",
    response_model=ExecutionAttemptRecoveryRead,
)
async def run_execution_attempt_recovery(
    payload: ExecutionAttemptRecoveryRunRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> ExecutionAttemptRecoveryRead:
    try:
        result = await execution_attempts.run_execution_attempt_recovery(
            session,
            tenant_id=context.tenant_id,
            settings=settings,
            dry_run=payload.dry_run,
            limit=payload.limit,
        )
    except execution_attempts.ExecutionAttemptRejected as exc:
        await session.rollback()
        raise execution_attempt_rejection(exc) from exc
    if not payload.dry_run:
        await session.commit()
    return result


@router.get("/tool-catalog", response_model=list[ToolDescriptorRead])
async def get_tool_catalog(
    _: TenantContext = Depends(get_tenant_context),
) -> list[ToolDescriptorRead]:
    return [
        ToolDescriptorRead(
            key=item.key,
            purpose=item.purpose,
            provider=item.provider,
            risk=item.risk.value,
            required_permissions=list(item.required_permissions),
            side_effects=item.side_effects,
            approval_required=item.approval_required,
        )
        for item in public_tool_catalog()
    ]


@router.get("/connector-catalog", response_model=list[ConnectorDescriptorRead])
async def get_connector_catalog(
    _: TenantContext = Depends(get_tenant_context),
) -> list[ConnectorDescriptorRead]:
    return [
        ConnectorDescriptorRead(
            key=item.key,
            version=item.version,
            provider=item.provider,
            purpose=item.purpose,
            action_types=list(item.action_types),
            action_contracts=[
                ConnectorActionContractRead(
                    action_type=contract.action_type,
                    schema_id=contract.schema_id,
                    version=contract.version,
                )
                for contract in payload_contracts_for(item.action_types)
            ],
            risk=item.risk.value,
            side_effects=item.side_effects,
            approval_required=item.approval_required,
            ledger_preparation_available=item.ledger_preparation_available,
            ledger_claim_available=item.ledger_claim_available,
            external_execution_available=item.external_execution_available,
        )
        for item in public_connector_catalog()
    ]


@router.get("/connector-catalog/{connector_key}/actions/{action_type}/schema")
async def get_connector_payload_schema(
    connector_key: str,
    action_type: str,
    _: TenantContext = Depends(get_tenant_context),
) -> dict:
    try:
        require_connector_action(connector_key, action_type, phase="prepare")
    except ConnectorPolicyError as exc:
        status_code = 404 if exc.code == "connector_not_registered" else 409
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": exc.detail},
        ) from exc
    return public_payload_schema(action_type)


@router.get("/attention", response_model=AttentionQueueRead)
async def get_attention_queue(
    minimum_level: AttentionLevel = Query(
        default=AttentionLevel.INFO,
        alias="min_level",
    ),
    kind: AttentionKind | None = Query(default=None),
    include_acknowledged: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> AttentionQueueRead:
    return await attention.build_attention_queue(
        session,
        context.tenant_id,
        settings=settings,
        minimum_level=minimum_level,
        kind=kind,
        include_acknowledged=include_acknowledged,
        limit=limit,
    )


@router.get(
    "/attention/automation-policy",
    response_model=AttentionAutomationPolicyRead,
)
async def get_attention_automation_policy(
    settings: Settings = Depends(get_settings),
    _: TenantContext = Depends(get_tenant_context),
) -> AttentionAutomationPolicyRead:
    return attention_automation.attention_automation_policy(settings)


@router.post(
    "/attention/automation/run",
    response_model=AttentionAutomationRunRead,
)
async def run_attention_automation(
    payload: AttentionAutomationRunRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> AttentionAutomationRunRead:
    try:
        result = await attention_automation.run_attention_automation(
            session,
            tenant_id=context.tenant_id,
            settings=settings,
            dry_run=payload.dry_run,
            limit=payload.limit,
            actor=context.actor,
        )
    except attention_automation.AttentionAutomationRejected as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.detail},
        ) from exc
    if not payload.dry_run:
        await session.commit()
    return result


def attention_acknowledgement_rejection(
    error: attention_acknowledgements.AttentionAcknowledgementRejected,
) -> HTTPException:
    status_code = 404 if error.code == "attention_not_found" else 409
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.detail},
    )


@router.get(
    "/attention/acknowledgements",
    response_model=list[AttentionAcknowledgementRead],
)
async def list_attention_acknowledgements(
    attention_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[AttentionAcknowledgement]:
    return await attention_acknowledgements.list_attention_acknowledgements(
        session,
        tenant_id=context.tenant_id,
        attention_id=attention_id,
        limit=limit,
    )


@router.post(
    "/attention/{attention_id}/acknowledgements",
    response_model=AttentionAcknowledgementRead,
    status_code=201,
)
async def acknowledge_attention(
    attention_id: str,
    payload: AttentionAcknowledgementCreate,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> AttentionAcknowledgement:
    try:
        acknowledgement = await attention_acknowledgements.acknowledge_attention(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            attention_id=attention_id,
            payload=payload,
            settings=settings,
        )
    except attention_acknowledgements.AttentionAcknowledgementRejected as exc:
        await session.rollback()
        raise attention_acknowledgement_rejection(exc) from exc
    await session.commit()
    await session.refresh(acknowledgement)
    return acknowledgement


def attention_follow_up_rejection(
    error: attention_follow_ups.AttentionFollowUpRejected,
) -> HTTPException:
    status_code = 404 if error.code in {"attention_not_found", "project_not_found"} else 409
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.detail},
    )


@router.get(
    "/attention/follow-ups",
    response_model=list[AttentionFollowUpRead],
)
async def list_attention_follow_ups(
    attention_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[AttentionFollowUpRead]:
    return await attention_follow_ups.list_attention_follow_ups(
        session,
        tenant_id=context.tenant_id,
        attention_id=attention_id,
        limit=limit,
    )


@router.post(
    "/attention/{attention_id}/follow-ups",
    response_model=AttentionFollowUpRead,
    status_code=201,
)
async def create_attention_follow_up(
    attention_id: str,
    payload: AttentionFollowUpCreate,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> AttentionFollowUpRead:
    try:
        follow_up = await attention_follow_ups.create_attention_follow_up(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            attention_id=attention_id,
            payload=payload,
            settings=settings,
        )
    except attention_follow_ups.AttentionFollowUpRejected as exc:
        await session.rollback()
        raise attention_follow_up_rejection(exc) from exc
    await session.commit()
    return follow_up


@router.get("/briefing-deliveries", response_model=list[BriefingDeliveryRead])
async def list_briefing_deliveries(
    status: BriefingDeliveryStatus | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[BriefingDelivery]:
    conditions = [BriefingDelivery.tenant_id == context.tenant_id]
    if status is not None:
        conditions.append(BriefingDelivery.status == status)
    query = (
        select(BriefingDelivery)
        .where(*conditions)
        .order_by(BriefingDelivery.scheduled_for.desc())
        .limit(limit)
    )
    return list(await session.scalars(query))


@router.get("/briefing-schedule", response_model=BriefingScheduleRead)
async def get_briefing_schedule(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> BriefingScheduleRead:
    last_delivery = (
        await session.scalars(
            select(BriefingDelivery)
            .where(BriefingDelivery.tenant_id == context.tenant_id)
            .order_by(BriefingDelivery.scheduled_for.desc())
            .limit(1)
        )
    ).first()
    return BriefingScheduleRead(
        enabled=settings.briefing_enabled and settings.telegram_enabled,
        timezone=settings.briefing_timezone,
        daily_time=f"{settings.briefing_hour:02d}:{settings.briefing_minute:02d}",
        quiet_hours=(
            f"{settings.briefing_quiet_start_hour:02d}:00-{settings.briefing_quiet_end_hour:02d}:00"
        ),
        catchup_hours=settings.briefing_catchup_hours,
        max_attempts=settings.briefing_max_attempts,
        last_delivery=last_delivery,
    )


@router.get("/ai-costs/current-month", response_model=AICostSummaryRead)
async def current_month_ai_costs(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> dict[str, object]:
    return await get_current_month_cost_summary(
        session,
        tenant_id=context.tenant_id,
        settings=settings,
    )


@router.get("/ai-costs/ledger", response_model=list[AICostLedgerRead])
async def list_ai_cost_ledger(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[AICostLedgerEntry]:
    return list(
        await session.scalars(
            select(AICostLedgerEntry)
            .where(AICostLedgerEntry.tenant_id == context.tenant_id)
            .order_by(AICostLedgerEntry.occurred_at.desc())
            .limit(limit)
        )
    )


async def require_task(session: AsyncSession, task_id: str, tenant_id: str) -> Task:
    query = select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id)
    task = (await session.scalars(query)).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def require_project(
    session: AsyncSession,
    project_id: str,
    tenant_id: str,
    *,
    for_update: bool = False,
) -> Project:
    query = select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
    if for_update:
        query = query.with_for_update()
    project = (await session.scalars(query)).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def require_goal(
    session: AsyncSession,
    goal_id: str,
    tenant_id: str,
    *,
    for_update: bool = False,
) -> Goal:
    query = select(Goal).where(Goal.id == goal_id, Goal.tenant_id == tenant_id)
    if for_update:
        query = query.with_for_update()
    goal = (await session.scalars(query)).first()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


async def require_decision(
    session: AsyncSession,
    decision_id: str,
    tenant_id: str,
) -> Decision:
    query = select(Decision).where(
        Decision.id == decision_id,
        Decision.tenant_id == tenant_id,
    )
    item = (await session.scalars(query)).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return item


async def require_commitment(
    session: AsyncSession,
    commitment_id: str,
    tenant_id: str,
) -> Commitment:
    query = select(Commitment).where(
        Commitment.id == commitment_id,
        Commitment.tenant_id == tenant_id,
    )
    item = (await session.scalars(query)).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Commitment not found")
    return item


def decision_rejection(error: decision_memory.DecisionLifecycleRejected) -> HTTPException:
    status_code = 404 if error.code.endswith("_not_found") else 409
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.detail},
    )


def commitment_rejection(
    error: commitments.CommitmentLifecycleRejected,
) -> HTTPException:
    status_code = 404 if error.code.endswith("_not_found") else 409
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.detail},
    )


def portfolio_rejection(error: portfolio.PortfolioLifecycleRejected) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": error.code, "message": error.detail},
    )


@router.get("/portfolio/health", response_model=PortfolioHealthRead)
async def get_portfolio_health(
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> PortfolioHealthRead:
    return await portfolio_health.build_portfolio_health(
        session,
        context.tenant_id,
        item_limit=limit,
    )


@router.post("/goals", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Goal:
    goal = Goal(tenant_id=context.tenant_id, **payload.model_dump())
    session.add(goal)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=context.actor,
        action="goal.created",
        resource_type="goal",
        resource_id=goal.id,
        details={"status": goal.status, "target_date": str(goal.target_date or "")},
    )
    await session.commit()
    await session.refresh(goal)
    return goal


@router.get("/goals", response_model=list[GoalRead])
async def list_goals(
    status_filter: str | None = Query(default=None, alias="status", max_length=40),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[Goal]:
    query = select(Goal).where(Goal.tenant_id == context.tenant_id)
    if status_filter:
        query = query.where(Goal.status == status_filter)
    query = query.order_by(Goal.created_at.desc()).limit(limit)
    return list(await session.scalars(query))


@router.get("/goals/{goal_id}", response_model=GoalRead)
async def get_goal(
    goal_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Goal:
    return await require_goal(session, goal_id, context.tenant_id)


@router.post("/goals/{goal_id}/transition", response_model=GoalRead)
async def transition_goal(
    goal_id: str,
    payload: GoalTransition,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Goal:
    goal = await require_goal(session, goal_id, context.tenant_id, for_update=True)
    try:
        await portfolio.transition_goal(
            session,
            item=goal,
            tenant_id=context.tenant_id,
            actor=context.actor,
            payload=payload,
        )
    except portfolio.PortfolioLifecycleRejected as exc:
        raise portfolio_rejection(exc) from exc
    await session.commit()
    await session.refresh(goal)
    return goal


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Project:
    if payload.goal_id:
        goal = await require_goal(
            session,
            payload.goal_id,
            context.tenant_id,
            for_update=True,
        )
        try:
            portfolio.ensure_goal_accepts_projects(goal)
        except portfolio.PortfolioLifecycleRejected as exc:
            raise portfolio_rejection(exc) from exc
    project = Project(tenant_id=context.tenant_id, **payload.model_dump())
    session.add(project)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=context.actor,
        action="project.created",
        resource_type="project",
        resource_id=project.id,
        details={"goal_id": project.goal_id},
    )
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(
    goal_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[Project]:
    query = select(Project).where(Project.tenant_id == context.tenant_id)
    if goal_id:
        await require_goal(session, goal_id, context.tenant_id)
        query = query.where(Project.goal_id == goal_id)
    query = query.order_by(Project.created_at.desc()).limit(limit)
    return list(await session.scalars(query))


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Project:
    return await require_project(session, project_id, context.tenant_id)


@router.post("/projects/{project_id}/transition", response_model=ProjectRead)
async def transition_project(
    project_id: str,
    payload: ProjectTransition,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Project:
    project = await require_project(session, project_id, context.tenant_id, for_update=True)
    try:
        await portfolio.transition_project(
            session,
            item=project,
            tenant_id=context.tenant_id,
            actor=context.actor,
            payload=payload,
        )
    except portfolio.PortfolioLifecycleRejected as exc:
        raise portfolio_rejection(exc) from exc
    await session.commit()
    await session.refresh(project)
    return project


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
    if payload.project_id:
        project = await require_project(
            session,
            payload.project_id,
            context.tenant_id,
            for_update=True,
        )
        try:
            portfolio.ensure_project_accepts_tasks(project)
        except portfolio.PortfolioLifecycleRejected as exc:
            raise portfolio_rejection(exc) from exc
    if payload.parent_task_id:
        parent = await require_task(session, payload.parent_task_id, context.tenant_id)
        if payload.project_id and parent.project_id != payload.project_id:
            raise HTTPException(
                status_code=409,
                detail="Parent task must belong to the same project",
            )
        if not payload.project_id and parent.project_id:
            raise HTTPException(
                status_code=409,
                detail="Child task must specify its parent project",
            )
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
        details={"project_id": task.project_id, "parent_task_id": task.parent_task_id},
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


@router.post(
    "/tasks/{task_id}/delegations",
    response_model=DelegationRead,
    status_code=status.HTTP_201_CREATED,
)
async def delegate_task(
    task_id: str,
    payload: DelegatedTaskCreate,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> Delegation:
    parent = await require_task(session, task_id, context.tenant_id)
    try:
        delegation, child = await create_delegation(
            session,
            parent=parent,
            payload=payload,
            settings=settings,
            initiator=context.actor,
        )
    except DelegationRejected as exc:
        add_audit_event(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            action="task.delegation_rejected",
            resource_type="task",
            resource_id=parent.id,
            details={"code": exc.code, "delegated_role": payload.delegated_role},
        )
        await session.commit()
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=context.actor,
        action="task.delegated",
        resource_type="delegation",
        resource_id=delegation.id,
        details={
            "parent_task_id": parent.id,
            "child_task_id": child.id,
            "project_id": parent.project_id,
            "initiator": context.actor,
            "reason": payload.reason,
            "delegated_role": payload.delegated_role,
            "depth": delegation.depth,
            "approval_id": delegation.approval_id,
        },
    )
    if delegation.approval_id:
        approval = await session.get(Approval, delegation.approval_id)
        add_audit_event(
            session,
            tenant_id=context.tenant_id,
            actor="system",
            action="approval.requested",
            resource_type="approval",
            resource_id=delegation.approval_id,
            details={
                "task_id": child.id,
                "risk": approval.risk if approval else "high",
                "delegation_id": delegation.id,
            },
        )
    await session.commit()
    await session.refresh(delegation)
    return delegation


@router.get("/tasks/{task_id}/delegations", response_model=list[DelegationRead])
async def list_task_delegations(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[Delegation]:
    await require_task(session, task_id, context.tenant_id)
    query = (
        select(Delegation)
        .where(
            Delegation.tenant_id == context.tenant_id,
            Delegation.parent_task_id == task_id,
        )
        .order_by(Delegation.created_at.asc())
    )
    return list(await session.scalars(query))


@router.get("/delegations/{delegation_id}", response_model=DelegationRead)
async def get_delegation(
    delegation_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Delegation:
    delegation = await session.scalar(
        select(Delegation).where(
            Delegation.id == delegation_id,
            Delegation.tenant_id == context.tenant_id,
        )
    )
    if delegation is None:
        raise HTTPException(status_code=404, detail="Delegation not found")
    return delegation


@router.post("/delegations/recover-stale", response_model=DelegationRecoveryResponse)
async def recover_stale_delegation_runs(
    payload: DelegationRecoveryRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> dict[str, object]:
    return await recover_stale_delegations(
        session,
        settings=settings,
        tenant_id=context.tenant_id,
        actor=context.actor,
        dry_run=payload.dry_run,
        limit=payload.limit,
    )


@router.post(
    "/delegations/{delegation_id}/run",
    response_model=DelegationDispatchResponse,
    status_code=202,
)
async def run_delegation(
    delegation_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    context: TenantContext = Depends(get_tenant_context),
) -> DelegationDispatchResponse:
    delegation = await session.scalar(
        select(Delegation).where(
            Delegation.id == delegation_id,
            Delegation.tenant_id == context.tenant_id,
        )
    )
    if delegation is None:
        raise HTTPException(status_code=404, detail="Delegation not found")
    try:
        child = await dispatch_delegation(
            session,
            delegation,
            settings,
            actor=context.actor,
        )
    except DelegationExecutionRejected as exc:
        add_audit_event(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            action="delegation.execution_rejected",
            resource_type="delegation",
            resource_id=delegation.id,
            details={"code": exc.code},
        )
        await session.commit()
        raise HTTPException(status_code=409, detail=exc.detail) from exc

    if settings.task_execution_mode == "worker":
        from app.worker import execute_delegation_job

        try:
            execute_delegation_job.delay(delegation.id)
        except Exception as exc:
            await release_delegation_cost_reservation(session, delegation, settings)
            delegation.status = "created"
            delegation.error = f"Queue dispatch failed: {type(exc).__name__}"
            child.status = child.status.QUEUED
            child.error = delegation.error
            add_audit_event(
                session,
                tenant_id=context.tenant_id,
                actor="system",
                action="delegation.dispatch_failed",
                resource_type="delegation",
                resource_id=delegation.id,
                details={"error_type": type(exc).__name__},
            )
            await session.commit()
            raise HTTPException(status_code=503, detail="Background queue is unavailable") from exc
    else:
        background_tasks.add_task(execute_delegation_with_new_session, delegation.id, False)
    return DelegationDispatchResponse(
        delegation_id=delegation.id,
        child_task_id=child.id,
        status=delegation.status,
        execution_mode=settings.task_execution_mode,
    )


@router.get("/tasks/{task_id}", response_model=TaskDetail)
async def get_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Task:
    query = (
        select(Task)
        .where(Task.id == task_id, Task.tenant_id == context.tenant_id)
        .options(selectinload(Task.runs).selectinload(TaskRun.workflow_run))
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
    if task.source == "delegation":
        raise HTTPException(
            status_code=409,
            detail="Delegated tasks must run through their delegation execution endpoint",
        )
    if task.status in {task.status.DISPATCHED, task.status.RUNNING}:
        raise HTTPException(status_code=409, detail="Task is already running")
    task.status = task.status.DISPATCHED
    await session.commit()
    if settings.task_execution_mode == "worker":
        from app.worker import execute_task_job

        try:
            execute_task_job.delay(task.id)
        except Exception as exc:
            task.status = task.status.QUEUED
            task.error = f"Queue dispatch failed: {type(exc).__name__}"
            add_audit_event(
                session,
                tenant_id=context.tenant_id,
                actor="system",
                action="task.dispatch_failed",
                resource_type="task",
                resource_id=task.id,
                details={"error_type": type(exc).__name__},
            )
            await session.commit()
            raise HTTPException(status_code=503, detail="Background queue is unavailable") from exc
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


@router.get("/workflow-definitions", response_model=list[WorkflowDefinitionRead])
async def list_workflow_definitions(
    session: AsyncSession = Depends(get_session),
    _: TenantContext = Depends(get_tenant_context),
) -> list[WorkflowDefinition]:
    await ensure_workflow_definitions(session)
    await session.commit()
    query = select(WorkflowDefinition).order_by(
        WorkflowDefinition.workflow_key, WorkflowDefinition.version
    )
    return list(await session.scalars(query))


@router.get("/workflow-runs/{workflow_run_id}", response_model=WorkflowRunRead)
async def get_workflow_run(
    workflow_run_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> WorkflowRun:
    query = select(WorkflowRun).where(
        WorkflowRun.id == workflow_run_id,
        WorkflowRun.tenant_id == context.tenant_id,
    )
    workflow_run = (await session.scalars(query)).first()
    if workflow_run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return workflow_run


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
    try:
        item = await decision_memory.create_decision(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            payload=payload,
        )
    except decision_memory.DecisionLifecycleRejected as error:
        raise decision_rejection(error) from error
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/decisions", response_model=list[DecisionRead])
async def list_decisions(
    decision_status: DecisionStatus | None = Query(default=None, alias="status"),
    decision_scope: DecisionScope | None = Query(default=None, alias="scope"),
    effective_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[Decision]:
    conditions = [Decision.tenant_id == context.tenant_id]
    if decision_status is not None:
        conditions.append(Decision.status == decision_status)
    if decision_scope is not None:
        conditions.append(Decision.scope == decision_scope)
    if effective_only:
        now = datetime.now(UTC)
        conditions.extend(
            [
                Decision.status == DecisionStatus.ACTIVE,
                Decision.effective_at <= now,
                or_(Decision.expires_at.is_(None), Decision.expires_at > now),
            ]
        )
    query = (
        select(Decision)
        .where(*conditions)
        .order_by(Decision.effective_at.desc(), Decision.created_at.desc())
        .limit(limit)
    )
    return list(await session.scalars(query))


@router.get("/decisions/readiness", response_model=DecisionReadinessRead)
async def get_decision_readiness(
    include_ready: bool = Query(default=False),
    include_closed: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> DecisionReadinessRead:
    return await decision_readiness.build_decision_readiness(
        session,
        context.tenant_id,
        include_ready=include_ready,
        include_closed=include_closed,
        limit=limit,
    )


@router.get("/decisions/follow-through", response_model=DecisionFollowThroughRead)
async def get_decision_follow_through(
    include_complete: bool = Query(default=False),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> DecisionFollowThroughRead:
    return await decision_follow_through.build_decision_follow_through(
        session,
        context.tenant_id,
        include_complete=include_complete,
        include_inactive=include_inactive,
        limit=limit,
    )


@router.get("/decisions/{decision_id}", response_model=DecisionRead)
async def get_decision(
    decision_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Decision:
    return await require_decision(session, decision_id, context.tenant_id)


@router.post("/decisions/{decision_id}/transition", response_model=DecisionRead)
async def transition_decision(
    decision_id: str,
    payload: DecisionTransition,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Decision:
    item = await require_decision(session, decision_id, context.tenant_id)
    try:
        await decision_memory.transition_decision(
            session,
            item=item,
            tenant_id=context.tenant_id,
            actor=context.actor,
            payload=payload,
        )
    except decision_memory.DecisionLifecycleRejected as error:
        raise decision_rejection(error) from error
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/commitments", response_model=CommitmentRead, status_code=201)
async def create_commitment(
    payload: CommitmentCreate,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Commitment:
    try:
        item = await commitments.create_commitment(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            payload=payload,
        )
    except commitments.CommitmentLifecycleRejected as error:
        raise commitment_rejection(error) from error
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/commitments", response_model=list[CommitmentRead])
async def list_commitments(
    commitment_status: CommitmentStatus | None = Query(default=None, alias="status"),
    owner_id: str | None = Query(default=None, max_length=100),
    project_id: str | None = Query(default=None, max_length=36),
    task_id: str | None = Query(default=None, max_length=36),
    decision_id: str | None = Query(default=None, max_length=36),
    due_before: datetime | None = Query(default=None),
    due_after: datetime | None = Query(default=None),
    overdue_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[Commitment]:
    conditions = [Commitment.tenant_id == context.tenant_id]
    if commitment_status is not None:
        conditions.append(Commitment.status == commitment_status)
    if owner_id is not None:
        conditions.append(Commitment.owner_id == owner_id)
    if project_id is not None:
        conditions.append(Commitment.project_id == project_id)
    if task_id is not None:
        conditions.append(Commitment.task_id == task_id)
    if decision_id is not None:
        conditions.append(Commitment.decision_id == decision_id)
    if due_before is not None:
        conditions.append(Commitment.due_at <= commitments.as_utc(due_before))
    if due_after is not None:
        conditions.append(Commitment.due_at >= commitments.as_utc(due_after))
    if overdue_only:
        conditions.extend(
            [
                Commitment.status.in_([CommitmentStatus.OPEN, CommitmentStatus.IN_PROGRESS]),
                Commitment.due_at < datetime.now(UTC),
            ]
        )
    query = (
        select(Commitment)
        .where(*conditions)
        .order_by(Commitment.due_at.asc(), Commitment.created_at.asc())
        .limit(limit)
    )
    return list(await session.scalars(query))


@router.get("/commitments/{commitment_id}", response_model=CommitmentRead)
async def get_commitment(
    commitment_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Commitment:
    return await require_commitment(session, commitment_id, context.tenant_id)


@router.post(
    "/commitments/{commitment_id}/transition",
    response_model=CommitmentRead,
)
async def transition_commitment(
    commitment_id: str,
    payload: CommitmentTransition,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> Commitment:
    item = await require_commitment(session, commitment_id, context.tenant_id)
    try:
        await commitments.transition_commitment(
            session,
            item=item,
            tenant_id=context.tenant_id,
            actor=context.actor,
            payload=payload,
        )
    except commitments.CommitmentLifecycleRejected as error:
        raise commitment_rejection(error) from error
    await session.commit()
    await session.refresh(item)
    return item


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


@router.get("/provenance", response_model=list[ProvenanceRead])
async def list_provenance(
    subject_type: ProvenanceSubjectType | None = Query(default=None),
    knowledge_item_id: str | None = Query(default=None, max_length=36),
    decision_id: str | None = Query(default=None, max_length=36),
    task_id: str | None = Query(default=None, max_length=36),
    verification_status: ProvenanceVerificationStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[ProvenanceRecord]:
    conditions = [ProvenanceRecord.tenant_id == context.tenant_id]
    if subject_type is not None:
        conditions.append(ProvenanceRecord.subject_type == subject_type)
    if knowledge_item_id is not None:
        conditions.append(ProvenanceRecord.knowledge_item_id == knowledge_item_id)
    if decision_id is not None:
        conditions.append(ProvenanceRecord.decision_id == decision_id)
    if task_id is not None:
        conditions.append(ProvenanceRecord.task_id == task_id)
    if verification_status is not None:
        conditions.append(ProvenanceRecord.verification_status == verification_status)
    query = (
        select(ProvenanceRecord)
        .where(*conditions)
        .order_by(ProvenanceRecord.captured_at.desc(), ProvenanceRecord.created_at.desc())
        .limit(limit)
    )
    return list(await session.scalars(query))


@router.get("/provenance/quality", response_model=ProvenanceQualityRead)
async def get_provenance_quality(
    include_verified: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> ProvenanceQualityRead:
    return await provenance_quality.build_provenance_quality(
        session,
        context.tenant_id,
        include_verified=include_verified,
        limit=limit,
    )


@router.get("/provenance/{record_id}", response_model=ProvenanceRead)
async def get_provenance(
    record_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> ProvenanceRecord:
    item = await session.scalar(
        select(ProvenanceRecord).where(
            ProvenanceRecord.id == record_id,
            ProvenanceRecord.tenant_id == context.tenant_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Provenance record not found")
    return item


def provenance_review_rejection(
    error: provenance_reviews.ProvenanceReviewRejected,
) -> HTTPException:
    status_code = 404 if error.code == "provenance_not_found" else 409
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.detail},
    )


@router.get(
    "/provenance/{record_id}/reviews",
    response_model=list[ProvenanceReviewRead],
)
async def list_provenance_reviews(
    record_id: str,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> list[ProvenanceReview]:
    try:
        await provenance_reviews.require_provenance_record(
            session,
            tenant_id=context.tenant_id,
            record_id=record_id,
        )
    except provenance_reviews.ProvenanceReviewRejected as exc:
        raise provenance_review_rejection(exc) from exc
    query = (
        select(ProvenanceReview)
        .where(
            ProvenanceReview.tenant_id == context.tenant_id,
            ProvenanceReview.provenance_record_id == record_id,
        )
        .order_by(ProvenanceReview.created_at.desc())
    )
    return list(await session.scalars(query))


@router.post(
    "/provenance/{record_id}/reviews",
    response_model=ProvenanceReviewRead,
    status_code=201,
)
async def review_provenance(
    record_id: str,
    payload: ProvenanceReviewCreate,
    session: AsyncSession = Depends(get_session),
    context: TenantContext = Depends(get_tenant_context),
) -> ProvenanceReview:
    try:
        review = await provenance_reviews.create_provenance_review(
            session,
            tenant_id=context.tenant_id,
            actor=context.actor,
            record_id=record_id,
            payload=payload,
        )
    except provenance_reviews.ProvenanceReviewRejected as exc:
        await session.rollback()
        raise provenance_review_rejection(exc) from exc
    await session.commit()
    await session.refresh(review)
    return review


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
    try:
        await action_intents.decide_linked_action_intent(
            session,
            approval=item,
            tenant_id=context.tenant_id,
            approved=payload.approved,
            actor=payload.decided_by,
        )
    except action_intents.ActionIntentRejected as exc:
        if exc.code == "intent_expired":
            await session.commit()
        else:
            await session.rollback()
        raise action_intent_rejection(exc) from exc
    item.status = ApprovalStatus.APPROVED if payload.approved else ApprovalStatus.REJECTED
    item.decided_by = payload.decided_by
    item.decision_note = payload.note
    item.decided_at = datetime.now(UTC)
    linked_delegation = await session.scalar(
        select(Delegation).where(
            Delegation.approval_id == item.id,
            Delegation.tenant_id == context.tenant_id,
        )
    )
    add_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor=payload.decided_by,
        action=f"approval.{item.status.value}",
        resource_type="approval",
        resource_id=item.id,
        details={"delegation_id": linked_delegation.id if linked_delegation else None},
    )
    if linked_delegation:
        add_audit_event(
            session,
            tenant_id=context.tenant_id,
            actor=payload.decided_by,
            action=f"delegation.approval_{item.status.value}",
            resource_type="delegation",
            resource_id=linked_delegation.id,
            details={"approval_id": item.id, "child_task_id": linked_delegation.child_task_id},
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
