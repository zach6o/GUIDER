import asyncio
from datetime import timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from app import models as m
from app.errors import GuideError
from app.guide.engine import record_event, transition
from app.guide.guard import vet_analysis, vet_instruction
from app.guide.planner import context_for, persist, steps_for
from app.guide.replan import (
    carried_verifications,
    context_for_replan,
    persist_replan,
    settled_steps,
)
from app.guide.steps import (
    confirmed_plan,
    next_open_step,
    publish_instruction,
    retire_instructions,
)
from app.imports.text import vet_import
from app.providers.base import ImportContext, InstructionContext
from app.schemas import Analysis
from app.service import purge_image, usable


async def run_plan(app, db, pending, session, request_id: str) -> None:
    """Role `plan`: propose, vet, persist, then hand the plan to the user for review.
    The worker never confirms a plan (ADR-010)."""
    try:
        if pending.deadline_at <= m.now():
            raise GuideError(503, "operation_timeout", "Planning timed out.")
        task = await db.get(m.GuideTask, pending.task_id)
        provider = app.state.providers.select("plan")
        proposal = await asyncio.wait_for(provider.plan(context_for(task)), timeout=30)
        plan = await persist(db, session, task, proposal)
        pending.result_ref = plan.id
        pending.status = "succeeded"
        await transition(db, session, "plan_ready", "plan_ready", request_id)
        await record_event(db, session, "plan.ready", request_id, {"plan_id": plan.id})
        await transition(
            db, session, "awaiting_user_confirmation", "plan_published", request_id
        )
        await record_event(
            db,
            session,
            "plan.confirmation_required",
            request_id,
            {"plan_id": plan.id, "version": plan.version},
        )
        await record_event(
            db, session, "operation.completed", request_id, {"operation_id": pending.id}
        )
    except (GuideError, OSError, ValueError, TimeoutError, ValidationError):
        pending.status = "failed"
        pending.error_code = "dependency_unavailable"
        await transition(
            db,
            session,
            session.checkpoint_state or "task_created",
            "plan_failed",
            request_id,
        )
        await record_event(
            db, session, "operation.failed", request_id, {"operation_id": pending.id}
        )


async def replan_reason(db, session) -> tuple[str, str]:
    """Why this task is being replanned, taken from what the session recorded
    rather than from anything a client asserted."""
    latest = await db.scalar(
        select(m.GuidanceEvent)
        .where(
            m.GuidanceEvent.session_id == session.id,
            m.GuidanceEvent.type == "session.stuck_detected",
        )
        .order_by(m.GuidanceEvent.sequence.desc())
        .limit(1)
    )
    recorded = (latest.payload or {}).get("reason", "") if latest else ""
    if recorded.startswith("anomaly:"):
        return "anomaly", recorded.split(":", 1)[1]
    return ("stuck", "none") if recorded else ("user", "none")


async def run_replan(app, db, pending, session, request_id: str) -> None:
    """Role `plan`, asked a second time: replace what is left of the roadmap.

    Settled steps are carried across exactly as they are, so nothing verified can
    be revised, un-verified or asked for again. The result is a draft the user
    reviews, like every other plan.
    """
    try:
        if pending.deadline_at <= m.now():
            raise GuideError(503, "operation_timeout", "Planning timed out.")
        task = await db.get(m.GuideTask, pending.task_id)
        previous = await confirmed_plan(db, session)
        done = await settled_steps(db, previous)
        reason, anomaly = await replan_reason(db, session)
        provider = app.state.providers.select("plan")
        proposal = await asyncio.wait_for(
            provider.plan(context_for_replan(task, done, reason, anomaly)), timeout=30
        )
        plan = await persist_replan(db, session, task, proposal, done)
        await carried_verifications(db, session, plan)
        pending.result_ref = plan.id
        pending.status = "succeeded"
        # A replacement roadmap is not confirmed and is not the one being
        # followed: the session waits on the user until they say otherwise.
        session.stuck_since = None
        await transition(db, session, "plan_ready", "replan_ready", request_id)
        await record_event(
            db,
            session,
            "plan.ready",
            request_id,
            {"plan_id": plan.id, "reason": reason, "carried_steps": len(done)},
        )
        await transition(db, session, "awaiting_user_confirmation", "replan_published", request_id)
        await record_event(
            db,
            session,
            "plan.confirmation_required",
            request_id,
            {"plan_id": plan.id, "version": plan.version},
        )
        await record_event(
            db, session, "operation.completed", request_id, {"operation_id": pending.id}
        )
    except (GuideError, OSError, ValueError, TimeoutError, ValidationError):
        pending.status = "failed"
        pending.error_code = "dependency_unavailable"
        # A failed replan writes nothing: the plan being followed is still the
        # confirmed one, and the checkpoint is the step the user was on. Doc 05
        # has no analyzing -> awaiting_user_action row, so recovery goes through
        # `blocked`, exactly as a failed instruction does.
        await transition(db, session, "blocked", "replan_failed", request_id)
        await record_event(
            db, session, "operation.failed", request_id, {"operation_id": pending.id}
        )


async def run_import(app, db, pending, session, request_id: str) -> None:
    """Role `import`: a pasted transcript to a draft plan, and nothing more.

    The guard runs between the importer and the database, so text that addresses
    Guider never reaches the goal and an injected step is dropped before anyone
    sees it as something to review. A restricted action *is* kept and marked
    `block` by `step_policy`, because the user should see what the conversation
    suggested and why Guider will not do it (ADR-012, ADR-018).
    """
    try:
        if pending.deadline_at <= m.now():
            raise GuideError(503, "operation_timeout", "Reading the conversation timed out.")
        task = await db.get(m.GuideTask, pending.task_id)
        imported = await db.scalar(
            select(m.ImportedConversation).where(
                m.ImportedConversation.owner_id == session.owner_id,
                m.ImportedConversation.session_id == session.id,
            )
        )
        if imported is None:
            raise GuideError(404, "not_found", "That import is no longer available.")
        provider = app.state.providers.select("import")
        proposal = vet_import(
            await asyncio.wait_for(
                provider.import_conversation(
                    ImportContext(transcript=imported.transcript, source=imported.source)
                ),
                timeout=30,
            )
        )
        # The goal is the vetted one, never the raw text.
        task.goal = proposal.goal
        task.title = proposal.goal[:120]
        if proposal.application_key and proposal.application_key != "unknown":
            task.application_key = proposal.application_key
        task.updated_at = m.now()
        plan = await persist(db, session, task, proposal.plan)
        steps = await steps_for(db, plan)
        imported.extracted_goal = proposal.goal
        imported.steps_extracted = len(steps)
        imported.steps_blocked = len(
            [step for step in steps if step.policy_disposition == "block"]
        )
        imported.updated_at = m.now()
        pending.result_ref = plan.id
        pending.status = "succeeded"
        await transition(db, session, "plan_ready", "import_ready", request_id)
        await record_event(
            db,
            session,
            "plan.ready",
            request_id,
            {
                "plan_id": plan.id,
                "imported": True,
                "source": imported.source,
                "steps_blocked": imported.steps_blocked,
            },
        )
        await transition(db, session, "awaiting_user_confirmation", "import_published", request_id)
        await record_event(
            db,
            session,
            "plan.confirmation_required",
            request_id,
            {"plan_id": plan.id, "version": plan.version},
        )
        await record_event(
            db, session, "operation.completed", request_id, {"operation_id": pending.id}
        )
    except (GuideError, OSError, ValueError, TimeoutError, ValidationError):
        pending.status = "failed"
        pending.error_code = "dependency_unavailable"
        await transition(db, session, "task_created", "import_failed", request_id)
        await record_event(
            db, session, "operation.failed", request_id, {"operation_id": pending.id}
        )


async def run_instruction(app, db, pending, session, request_id: str) -> None:
    """Role `instruct`: publish one action for the current step.

    active -> processing -> instruction_ready -> awaiting_user_action, per doc 05.
    The worker never marks a step done; only evidence or the user can speak to that.
    """
    try:
        if pending.deadline_at <= m.now():
            raise GuideError(503, "operation_timeout", "Preparing the step timed out.")
        await transition(db, session, "processing", "instruction_requested", request_id)
        plan = await confirmed_plan(db, session)
        step = await next_open_step(db, plan)
        if step is None:
            pending.status = "succeeded"
            session.current_step_id = None
            # Nothing is waiting on the user, so nothing may still read as the
            # current instruction: a stale one would invite a claim on a step
            # that is already behind the guide.
            await retire_instructions(db, session)
            await transition(db, session, "awaiting_user_action", "steps_exhausted", request_id)
            await record_event(
                db, session, "plan.steps_exhausted", request_id, {"plan_id": plan.id}
            )
            return
        task = await db.get(m.GuideTask, pending.task_id)
        provider = app.state.providers.select("instruct")
        proposal = vet_instruction(
            await asyncio.wait_for(
                provider.instruct(
                    InstructionContext(
                        goal=task.goal,
                        application_key=step.application_key,
                        title=step.title,
                        action=step.action,
                        expected_result=step.expected_result,
                        fallback=step.fallback,
                        explanation=step.explanation,
                        ordinal=step.ordinal,
                        total_steps=len(await steps_for(db, plan)),
                    )
                ),
                timeout=30,
            )
        )
        instruction = await publish_instruction(db, session, step, proposal, request_id)
        pending.result_ref = instruction.id
        pending.status = "succeeded"
        await transition(db, session, "instruction_ready", "instruction_ready", request_id)
        await transition(db, session, "awaiting_user_action", "instruction_published", request_id)
        step.status = "awaiting_user_action"
        await record_event(db, session, "step.awaiting_action", request_id, {"step_id": step.id})
        await record_event(
            db, session, "operation.completed", request_id, {"operation_id": pending.id}
        )
    except (GuideError, OSError, ValueError, TimeoutError, ValidationError):
        pending.status = "failed"
        pending.error_code = "dependency_unavailable"
        await transition(
            db, session, "blocked", "instruction_failed", request_id
        )
        await record_event(
            db, session, "operation.failed", request_id, {"operation_id": pending.id}
        )


async def tick(app) -> None:
    async with app.state.sessions() as db, db.begin():
        pending = await db.scalar(
            select(m.OperationRow)
            .where(
                m.OperationRow.status == "queued",
            )
            .order_by(m.OperationRow.created_at)
            .limit(1)
        )
        if pending is None:
            return
        # The first slice has a single local worker. Owner lock also guards web mutations.
        await db.scalar(select(m.User).where(m.User.id == pending.owner_id).with_for_update())
        await db.refresh(pending)
        session = await db.get(m.GuideSession, pending.session_id)
        if pending.status != "queued":
            return
        request_id = str(uuid4())
        if (
            session.state_version != pending.expected_state_version
            or session.control_epoch != pending.control_epoch
            or session.expires_at <= m.now()
        ):
            pending.status = "canceled"
            if session.state == "analyzing":
                await transition(
                    db,
                    session,
                    session.checkpoint_state or "task_created",
                    "stale_operation",
                    request_id,
                )
            return
        pending.status = "running"
        pending.attempt_count += 1
        if pending.kind in {"plan", "instruct", "replan", "import"}:
            handler = {
                "plan": run_plan,
                "instruct": run_instruction,
                "replan": run_replan,
                "import": run_import,
            }[pending.kind]
            await handler(app, db, pending, session, request_id)
            pending.completed_at = m.now()
            return
        try:
            if pending.deadline_at <= m.now():
                raise GuideError(503, "operation_timeout", "Analysis timed out.")
            images = list(
                await db.scalars(
                    select(m.ScreenshotRow)
                    .join(
                        m.OperationEvidence,
                        m.OperationEvidence.screenshot_id == m.ScreenshotRow.id,
                    )
                    .where(m.OperationEvidence.operation_id == pending.id)
                )
            )
            pixels = []
            for image in images:
                usable(image)
                pixels.append((image.id, await app.state.storage.read(image.object_key)))
            # The adapter cannot approve its own output; the guard decides.
            result = vet_analysis(
                Analysis.model_validate(
                    await asyncio.wait_for(
                        app.state.provider.analyze(pixels),
                        timeout=10,
                    )
                )
            )
            if {str(value) for value in result.screenshot_ids} != {im.id for im in images}:
                raise ValueError("Provider returned unrelated evidence")
            row = m.AnalysisRow(
                id=str(result.id),
                owner_id=pending.owner_id,
                task_id=pending.task_id,
                session_id=pending.session_id,
                observations=[item.model_dump() for item in result.observations],
                explanation=result.explanation,
                needs_context=result.needs_context,
                context_request=result.context_request,
                expires_at=min(image.expires_at for image in images),
            )
            db.add(row)
            pending.result_ref = row.id
            pending.status = "succeeded"
            if session.state == "analyzing":
                await transition(
                    db,
                    session,
                    session.checkpoint_state or "task_created",
                    "explanation_ready",
                    request_id,
                )
            else:
                await transition(db, session, session.state, "explanation_ready", request_id)
            await record_event(db, session, "analysis.ready", request_id, {"analysis_id": row.id})
            await record_event(
                db, session, "operation.completed", request_id, {"operation_id": pending.id}
            )
        except (GuideError, OSError, ValueError, TimeoutError):
            pending.status = "failed"
            pending.error_code = "dependency_unavailable"
            if session.state == "analyzing":
                await transition(
                    db,
                    session,
                    session.checkpoint_state or "task_created",
                    "analysis_failed",
                    request_id,
                )
            await record_event(
                db, session, "operation.failed", request_id, {"operation_id": pending.id}
            )
        pending.completed_at = m.now()


async def sweep(app) -> None:
    async with app.state.sessions() as db, db.begin():
        expired = list(
            await db.scalars(
                select(m.ScreenshotRow)
                .where(
                    m.ScreenshotRow.expires_at <= m.now(),
                    m.ScreenshotRow.object_key.is_not(None),
                )
                .limit(100)
            )
        )
        for image in expired:
            await db.scalar(select(m.User).where(m.User.id == image.owner_id).with_for_update())
            await purge_image(db, app.state.storage, image, str(uuid4()))


async def run_worker(app) -> None:
    next_sweep = m.now()
    while True:
        try:
            await tick(app)
            if m.now() >= next_sweep:
                await sweep(app)
                next_sweep = m.now() + timedelta(minutes=1)
        except Exception:
            # Do not log SQL, image bytes, user text or provider payloads.
            app.state.worker_healthy = False
        else:
            app.state.worker_healthy = True
        await asyncio.sleep(0.5)
