import asyncio
import time
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import explicit_workflow, orchestrate
from app.core.config import get_settings
from app.models import Approval, KnowledgeItem, Task, TaskRun, TaskStatus, WorkflowRun
from app.services.audit import add_audit_event
from app.services.company_context import build_company_context
from app.workflows.catalog import (
    build_execution_plan,
    ensure_workflow_definitions,
    get_workflow_template,
)


class TaskExecutionError(RuntimeError):
    pass


async def execute_task(
    session: AsyncSession,
    task_id: str,
    *,
    raise_on_failure: bool = False,
    recover_running: bool = False,
) -> None:
    task = await session.get(Task, task_id)
    if task is None:
        raise LookupError(f"Task {task_id} not found")
    if task.status == TaskStatus.COMPLETED:
        return
    if task.status == TaskStatus.RUNNING:
        if not recover_running:
            return

    expected_status = task.status
    expected_updated_at = task.updated_at
    claim_time = datetime.now(UTC)
    claim = await session.execute(
        update(Task)
        .where(
            Task.id == task.id,
            Task.status == expected_status,
            Task.updated_at == expected_updated_at,
        )
        .values(status=TaskStatus.RUNNING, error=None, updated_at=claim_time)
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount != 1:
        await session.rollback()
        return
    task.status = TaskStatus.RUNNING
    task.error = None
    task.updated_at = claim_time

    if expected_status == TaskStatus.RUNNING:
        running_runs = list(
            await session.scalars(
                select(TaskRun).where(
                    TaskRun.task_id == task.id,
                    TaskRun.status == TaskStatus.RUNNING,
                )
            )
        )
        for interrupted_run in running_runs:
            interrupted_run.status = TaskStatus.FAILED
            interrupted_run.feedback = "Recovered after background worker redelivery"
            interrupted_run.finished_at = datetime.now(UTC)
        if running_runs:
            interrupted_workflows = list(
                await session.scalars(
                    select(WorkflowRun).where(
                        WorkflowRun.task_run_id.in_([item.id for item in running_runs])
                    )
                )
            )
            for interrupted_workflow in interrupted_workflows:
                interrupted_workflow.status = "failed"
                interrupted_workflow.error = "Recovered after background worker redelivery"
                interrupted_workflow.finished_at = datetime.now(UTC)
        add_audit_event(
            session,
            tenant_id=task.tenant_id,
            actor="system",
            action="task.recovered",
            resource_type="task",
            resource_id=task.id,
            details={"interrupted_runs": len(running_runs)},
        )

    attempt_query = select(func.count(TaskRun.id)).where(TaskRun.task_id == task.id)
    attempt = int((await session.scalar(attempt_query)) or 0) + 1
    run = TaskRun(task_id=task.id, status=TaskStatus.RUNNING, attempt=attempt)
    session.add(run)
    await session.flush()
    settings = get_settings()
    selected_workflow = explicit_workflow(task.request)
    template = get_workflow_template(selected_workflow)
    definitions = await ensure_workflow_definitions(session)
    definition = definitions[template["workflow_key"]]
    execution_plan = build_execution_plan(
        selected_workflow,
        max_reworks=settings.review_max_reworks,
        provider=settings.ai_provider,
        model=settings.openai_model,
    )
    workflow_run = WorkflowRun(
        tenant_id=task.tenant_id,
        task_id=task.id,
        task_run_id=run.id,
        definition_id=definition.id,
        workflow_key=template["workflow_key"],
        workflow_version=template["version"],
        status="running",
        definition_snapshot=template,
        execution_plan=execution_plan,
    )
    session.add(workflow_run)
    add_audit_event(
        session,
        tenant_id=task.tenant_id,
        actor="system",
        action="task.started",
        resource_type="task",
        resource_id=task.id,
        details={
            "attempt": attempt,
            "workflow_key": template["workflow_key"],
            "workflow_version": template["version"],
        },
    )
    await session.commit()

    started = time.perf_counter()
    caught: Exception | None = None
    try:
        company_context = await build_company_context(session, task.tenant_id)
        outcome = await asyncio.wait_for(
            orchestrate(task.request, settings, company_context),
            timeout=settings.task_timeout_seconds,
        )
        task.result = outcome.final_report
        task.status = TaskStatus.COMPLETED
        run.status = TaskStatus.COMPLETED
        run.verdict = outcome.verdict
        run.feedback = outcome.feedback
        run.artifacts = outcome.artifacts()
        run.input_tokens = outcome.input_tokens
        run.output_tokens = outcome.output_tokens
        run.total_tokens = outcome.total_tokens
        run.finished_at = datetime.now(UTC)
        run.duration_ms = round((time.perf_counter() - started) * 1000)
        workflow_run.status = "completed"
        workflow_run.result_summary = {
            "selected_workflow": outcome.workflow,
            "verdict": outcome.verdict.value,
            "rework_count": outcome.rework_count,
            "total_tokens": outcome.total_tokens,
            "completed_steps": [step["key"] for step in execution_plan["steps"]],
        }
        workflow_run.finished_at = run.finished_at
        existing_knowledge = await session.scalar(
            select(KnowledgeItem.id).where(
                KnowledgeItem.tenant_id == task.tenant_id,
                KnowledgeItem.task_id == task.id,
                KnowledgeItem.source == "Research Agent",
            )
        )
        if existing_knowledge is None:
            session.add(
                KnowledgeItem(
                    tenant_id=task.tenant_id,
                    title=f"Research: {task.title}",
                    content=outcome.research,
                    source="Research Agent",
                    task_id=task.id,
                )
            )

        existing_approval_actions = set(
            await session.scalars(
                select(Approval.action).where(
                    Approval.tenant_id == task.tenant_id,
                    Approval.task_id == task.id,
                )
            )
        )
        for approval_request in outcome.approval_requests:
            if approval_request.action in existing_approval_actions:
                continue
            approval = Approval(
                tenant_id=task.tenant_id,
                task_id=task.id,
                action=approval_request.action,
                reason=approval_request.reason,
                risk=approval_request.risk,
            )
            session.add(approval)
            await session.flush()
            add_audit_event(
                session,
                tenant_id=task.tenant_id,
                actor="Chief of Staff",
                action="approval.requested",
                resource_type="approval",
                resource_id=approval.id,
                details={"task_id": task.id, "risk": approval_request.risk},
            )
            existing_approval_actions.add(approval_request.action)
        add_audit_event(
            session,
            tenant_id=task.tenant_id,
            actor="system",
            action="task.completed",
            resource_type="task",
            resource_id=task.id,
            details={
                "attempt": attempt,
                "total_tokens": outcome.total_tokens,
                "workflow_run_id": workflow_run.id,
                "workflow_key": workflow_run.workflow_key,
                "workflow_version": workflow_run.workflow_version,
            },
        )
    except Exception as exc:
        caught = exc
        task.status = TaskStatus.FAILED
        task.error = f"{type(exc).__name__}: {exc}"
        run.status = TaskStatus.FAILED
        run.feedback = task.error
        run.finished_at = datetime.now(UTC)
        run.duration_ms = round((time.perf_counter() - started) * 1000)
        workflow_run.status = "failed"
        workflow_run.error = task.error
        workflow_run.finished_at = run.finished_at
        add_audit_event(
            session,
            tenant_id=task.tenant_id,
            actor="system",
            action="task.failed",
            resource_type="task",
            resource_id=task.id,
            details={
                "attempt": attempt,
                "error": task.error,
                "workflow_run_id": workflow_run.id,
                "workflow_key": workflow_run.workflow_key,
                "workflow_version": workflow_run.workflow_version,
            },
        )
    await session.commit()
    if caught is None and task.source == "telegram" and task.external_ref:
        from app.services.telegram import send_telegram_message

        delivered = await send_telegram_message(
            get_settings(),
            task.external_ref,
            f"업무 완료: {task.title}\n\n{task.result or '(결과 없음)'}",
        )
        add_audit_event(
            session,
            tenant_id=task.tenant_id,
            actor="system",
            action=("telegram.notification.sent" if delivered else "telegram.notification.failed"),
            resource_type="task",
            resource_id=task.id,
            details={"chat_id": task.external_ref},
        )
        await session.commit()
    if caught and raise_on_failure:
        raise TaskExecutionError(str(caught)) from caught


async def execute_task_with_new_session(
    task_id: str,
    retry_inline: bool = True,
    raise_on_failure: bool = False,
    recover_running: bool = False,
) -> None:
    from app.db import SessionLocal

    settings = get_settings()
    attempts = settings.task_max_attempts if retry_inline else 1
    last_error: TaskExecutionError | None = None
    for attempt_number in range(attempts):
        try:
            async with SessionLocal() as session:
                await execute_task(
                    session,
                    task_id,
                    raise_on_failure=True,
                    recover_running=recover_running,
                )
            return
        except TaskExecutionError as exc:
            last_error = exc
            if attempt_number + 1 < attempts:
                async with SessionLocal() as session:
                    task = await session.get(Task, task_id)
                    if task:
                        task.status = TaskStatus.DISPATCHED
                        await session.commit()
    if raise_on_failure and last_error:
        raise last_error
