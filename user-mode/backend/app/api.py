import asyncio
import time
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Query, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select

from app import models as m
from app import schemas as s
from app.auth import Db, Owner
from app.errors import GuideError, not_found
from app.guide.engine import ANALYSIS_STATES, PLAN_STATES, TERMINAL, record_event, transition
from app.guide.guard import vet_observation
from app.guide.observation import (
    MAX_OBSERVATION_CALLS,
    NOTICE_VERSION,
    apply,
    calls_remaining,
    check_budget,
    enable,
)
from app.guide.observation import stop as stop_watching
from app.guide.planner import steps_for
from app.guide.replan import check_stuck
from app.guide.steps import (
    confirmed_plan,
    current_instruction,
    owned_step,
    record_claim,
    record_self_report,
    retire_instructions,
    skip_step,
)
from app.imports.redact import MAX_TRANSCRIPT, redact
from app.media import MAX_BYTES, normalize, prepare_frame
from app.providers.base import ObserveContext
from app.service import (
    cancel_pending,
    check_version,
    current_plan_version,
    digest,
    operation_result,
    owned,
    purge_image,
    quota,
    read_events,
    remember,
    replay,
    usable,
)

router = APIRouter(prefix="/api/v1/guide", responses={
    status: {"model": s.ErrorEnvelope}
    for status in (400, 401, 403, 404, 409, 410, 413, 415, 422, 429, 503)
})
Key = Annotated[UUID, Header(alias="Idempotency-Key")]


def envelope(request: Request, data):
    return {"data": data, "request_id": request.state.request_id}


@router.post("/tasks", status_code=201, response_model=s.Envelope[s.CreatedTask])
async def create_task(body: s.TaskCreate, request: Request, db: Db, owner: Owner, key: Key):
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    await quota(db, m.GuideTask, owner.id, 10, 3600)
    task = m.GuideTask(
        id=m.new_id(),
        owner_id=owner.id,
        title=body.title or body.goal[:120],
        goal=body.goal,
        category=body.category,
        application_key=body.application_key,
        expires_at=m.now() + timedelta(days=30),
    )
    db.add(task)
    await db.flush()
    session = m.GuideSession(
        id=m.new_id(),
        owner_id=owner.id,
        task_id=task.id,
        expires_at=m.now() + timedelta(hours=24),
    )
    db.add(session)
    await db.flush()
    task.current_session_id = session.id
    await record_event(db, session, "task.created", request.state.request_id, {"task_id": task.id})
    result = s.CreatedTask(
        task=s.Task.model_validate(task), session=s.Session.model_validate(session)
    )
    await remember(db, request, owner.id, str(key), request_digest, result, 201)
    return envelope(request, result)


@router.post(
    "/imports/conversations", status_code=202, response_model=s.Envelope[s.ImportAccepted]
)
async def import_conversation(
    body: s.ImportRequest,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
):
    """Continue from a conversation the user already had somewhere else.

    The text is untrusted data in the SEC-09 sense: it is redacted, stored once
    for provenance, and read for a goal and candidate steps. What comes back is a
    draft plan the user confirms, like any other. An import cannot confirm a plan,
    start a session, switch watching on or change policy (ADR-018).
    """
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    if len(body.text.encode()) > MAX_TRANSCRIPT:
        raise GuideError(
            413, "payload_too_large", "Paste at most 32 KiB of conversation at a time."
        )
    await quota(db, m.GuideTask, owner.id, 10, 3600)
    # Secrets are dropped before the row is written, so nothing that was pasted
    # by accident is stored even for a moment (ADR-018).
    transcript, redactions = redact(body.text)

    task = m.GuideTask(
        id=m.new_id(),
        owner_id=owner.id,
        # The real goal comes from the vetted extraction; this is a placeholder the
        # worker replaces, never anything read out of the transcript.
        title="Imported conversation",
        goal="Imported conversation",
        category=body.category,
        application_key=body.application_key,
        expires_at=m.now() + timedelta(days=30),
    )
    db.add(task)
    await db.flush()
    session = m.GuideSession(
        id=m.new_id(),
        owner_id=owner.id,
        task_id=task.id,
        expires_at=m.now() + timedelta(hours=24),
    )
    db.add(session)
    await db.flush()
    task.current_session_id = session.id

    imported = m.ImportedConversation(
        id=m.new_id(),
        owner_id=owner.id,
        task_id=task.id,
        session_id=session.id,
        source=body.source,
        transcript=transcript,
        redactions=redactions,
        expires_at=m.now() + timedelta(days=30),
    )
    db.add(imported)
    await db.flush()
    await record_event(
        db,
        session,
        "task.created",
        request.state.request_id,
        {"imported": True, "source": body.source, "redactions": redactions},
    )
    await transition(db, session, "analyzing", "import_requested", request.state.request_id)
    operation = m.OperationRow(
        id=m.new_id(),
        owner_id=owner.id,
        task_id=task.id,
        session_id=session.id,
        kind="import",
        expected_state_version=session.state_version,
        control_epoch=session.control_epoch,
        request_digest=request_digest,
        deadline_at=m.now() + timedelta(seconds=65),
        expires_at=m.now() + timedelta(hours=24),
    )
    db.add(operation)
    await db.flush()
    await record_event(
        db, session, "operation.started", request.state.request_id, {"operation_id": operation.id}
    )
    result = s.ImportAccepted(
        task=s.Task.model_validate(task),
        session=s.Session.model_validate(session),
        operation_id=operation.id,
        imported=s.ImportedConversation.model_validate(imported),
    )
    await remember(db, request, owner.id, str(key), request_digest, result, 202)
    return envelope(request, result)


@router.get("/tasks/{task_id}", response_model=s.Envelope[s.Task])
async def get_task(task_id: UUID, request: Request, db: Db, owner: Owner):
    return envelope(request, await owned(db, m.GuideTask, str(task_id), owner.id))


@router.get("/sessions/{session_id}", response_model=s.Envelope[s.Session])
async def get_session(session_id: UUID, request: Request, db: Db, owner: Owner):
    return envelope(request, await owned(db, m.GuideSession, str(session_id), owner.id))


@router.get("/sessions", response_model=s.Envelope[s.SessionList])
async def sessions(
    request: Request,
    db: Db,
    owner: Owner,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: UUID | None = None,
    task_id: UUID | None = None,
    state: s.SessionState | None = None,
):
    query = (
        select(m.GuideSession, m.GuideTask.title)
        .join(
            m.GuideTask,
            m.GuideSession.task_id == m.GuideTask.id,
        )
        .where(m.GuideSession.owner_id == owner.id, m.GuideSession.deleted_at.is_(None))
    )
    if task_id:
        query = query.where(m.GuideSession.task_id == str(task_id))
    if state:
        query = query.where(m.GuideSession.state == state)
    if cursor:
        anchor = await owned(db, m.GuideSession, str(cursor), owner.id)
        if (task_id and anchor.task_id != str(task_id)) or (state and anchor.state != state):
            raise GuideError(400, "invalid_request", "This cursor does not match the filters.")
        query = query.where(
            (m.GuideSession.created_at < anchor.created_at)
            | ((m.GuideSession.created_at == anchor.created_at) & (m.GuideSession.id < anchor.id)),
        )
    rows = list(
        (
            await db.execute(
                query.order_by(
                    m.GuideSession.created_at.desc(),
                    m.GuideSession.id.desc(),
                ).limit(limit + 1)
            )
        ).all()
    )
    return envelope(
        request,
        s.SessionList(
            items=[
                s.SessionItem(session=s.Session.model_validate(row), task_title=title)
                for row, title in rows[:limit]
            ],
            next_cursor=rows[limit - 1][0].id if len(rows) > limit else None,
        ),
    )


async def plan_view(db: Db, plan: m.TaskPlan) -> s.Plan:
    return s.Plan(
        id=plan.id,
        task_id=plan.task_id,
        session_id=plan.session_id,
        version=plan.version,
        status=plan.status,
        assumptions=plan.assumptions,
        policy_version=plan.policy_version,
        confirmed_at=plan.confirmed_at,
        steps=[s.Step.model_validate(step) for step in await steps_for(db, plan)],
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.post("/tasks/{task_id}/plans", status_code=202, response_model=s.Envelope[s.Pending])
async def request_plan(
    task_id: UUID,
    body: s.PlanRequest,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
):
    task = await owned(db, m.GuideTask, str(task_id), owner.id)
    session = await owned(db, m.GuideSession, str(body.session_id), owner.id)
    if session.task_id != task.id:
        raise not_found()
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    check_version(session, body.expected_version)
    if session.state not in PLAN_STATES:
        raise GuideError(409, "invalid_transition", "Finish the current operation first.")
    if await db.scalar(
        select(m.OperationRow.id).where(
            m.OperationRow.session_id == session.id,
            m.OperationRow.status.in_(["queued", "running"]),
        )
    ):
        raise GuideError(409, "operation_in_progress", "An operation is already running.")
    await quota(db, m.OperationRow, owner.id, 10, 60)
    session.last_user_activity_at = m.now()
    session.checkpoint_state = session.state
    await transition(db, session, "analyzing", "plan_requested", request.state.request_id)
    operation = m.OperationRow(
        id=m.new_id(),
        owner_id=owner.id,
        task_id=task.id,
        session_id=session.id,
        kind="plan",
        expected_state_version=session.state_version,
        control_epoch=session.control_epoch,
        request_digest=request_digest,
        deadline_at=m.now() + timedelta(seconds=65),
        expires_at=m.now() + timedelta(hours=24),
    )
    db.add(operation)
    await db.flush()
    await record_event(
        db, session, "operation.started", request.state.request_id, {"operation_id": operation.id}
    )
    result = s.Pending(operation_id=operation.id, session=s.Session.model_validate(session))
    await remember(db, request, owner.id, str(key), request_digest, result, 202)
    return envelope(request, result)


@router.get("/plans/{plan_id}", response_model=s.Envelope[s.Plan])
async def get_plan(plan_id: UUID, request: Request, db: Db, owner: Owner):
    plan = await owned(db, m.TaskPlan, str(plan_id), owner.id)
    return envelope(request, await plan_view(db, plan))


@router.post("/plans/{plan_id}/confirm", response_model=s.Envelope[s.ConfirmedPlan])
async def confirm_plan(
    plan_id: UUID,
    body: s.ConfirmRequest,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
):
    plan = await owned(db, m.TaskPlan, str(plan_id), owner.id)
    session = await owned(db, m.GuideSession, plan.session_id, owner.id)
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    check_version(session, body.expected_version)
    # Confirmation binds one exact version. A superseded plan cannot start.
    if plan.status == "superseded" or plan.version != body.plan_version:
        raise GuideError(
            409,
            "stale_version",
            "This plan was replaced. Review the current plan before starting.",
            details={"current_version": await current_plan_version(db, session)},
        )
    if session.state != "awaiting_user_confirmation":
        raise GuideError(409, "invalid_transition", "This plan is not awaiting confirmation.")
    if plan.status == "draft":
        plan.status = "confirmed"
        plan.confirmed_at = m.now()
        plan.confirmed_by = owner.id
        plan.updated_at = m.now()
    session.confirmed_plan_version = plan.version
    session.last_user_activity_at = m.now()
    # Same-state command: version still advances, no session.state_changed event.
    await transition(
        db, session, session.state, "plan_confirmed", request.state.request_id
    )
    await record_event(
        db,
        session,
        "plan.confirmed",
        request.state.request_id,
        {"plan_id": plan.id, "version": plan.version},
    )
    result = s.ConfirmedPlan(
        plan=await plan_view(db, plan), session=s.Session.model_validate(session)
    )
    await remember(db, request, owner.id, str(key), request_digest, result, 200)
    return envelope(request, result)


def step_view(step: m.TaskStep) -> s.Step:
    return s.Step.model_validate(step)


@router.post("/sessions/{session_id}/start", status_code=202, response_model=s.Envelope[s.Pending])
async def start_session(
    session_id: UUID,
    body: s.StartRequest,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
):
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    check_version(session, body.expected_version)
    # Nothing starts without an explicitly confirmed plan version (ADR-010).
    plan = await confirmed_plan(db, session)
    await quota(db, m.OperationRow, owner.id, 10, 60)
    session.last_user_activity_at = m.now()
    session.observation_mode = body.observation_mode
    await transition(db, session, "active", "session_started", request.state.request_id)
    await record_event(
        db, session, "session.started", request.state.request_id, {"plan_id": plan.id}
    )
    operation = await queue_instruction(db, session, request.state.request_id)
    result = s.Pending(operation_id=operation.id, session=s.Session.model_validate(session))
    await remember(db, request, owner.id, str(key), request_digest, result, 202)
    return envelope(request, result)


async def queue_instruction(db: Db, session: m.GuideSession, request_id: str) -> m.OperationRow:
    operation = m.OperationRow(
        id=m.new_id(),
        owner_id=session.owner_id,
        task_id=session.task_id,
        session_id=session.id,
        kind="instruct",
        expected_state_version=session.state_version,
        control_epoch=session.control_epoch,
        request_digest=digest({"step": session.current_step_id, "v": session.state_version}),
        deadline_at=m.now() + timedelta(seconds=65),
        expires_at=m.now() + timedelta(hours=24),
    )
    db.add(operation)
    await db.flush()
    await record_event(db, session, "operation.started", request_id, {"operation_id": operation.id})
    return operation


@router.get("/sessions/{session_id}/instruction", response_model=s.Envelope[s.CurrentInstruction])
async def get_instruction(session_id: UUID, request: Request, db: Db, owner: Owner):
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    instruction = await current_instruction(db, session)
    if instruction is None:
        raise not_found()
    step = await owned_step(db, session, instruction.step_id)
    return envelope(
        request,
        s.CurrentInstruction(
            instruction=s.Instruction.model_validate(instruction),
            step=step_view(step),
            session=s.Session.model_validate(session),
        ),
    )


@router.post("/sessions/{session_id}/steps/{step_id}/claim", response_model=s.Envelope[s.Claimed])
async def claim_step(
    session_id: UUID,
    step_id: UUID,
    body: s.ClaimRequest,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
):
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    step = await owned_step(db, session, str(step_id))
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    check_version(session, body.expected_version)
    if session.state != "awaiting_user_action":
        raise GuideError(409, "invalid_transition", "There is no step waiting on you.")
    claim = await record_claim(db, session, step, body.statement, request.state.request_id)
    session.last_user_activity_at = m.now()
    instruction = await current_instruction(db, session)
    if instruction is not None:
        # Saying "done" repeatedly on the same step is the guide going nowhere.
        await check_stuck(db, session, step, instruction, "none", request.state.request_id)
    # Same-state: a claim is not progress, so the session does not move.
    await transition(db, session, session.state, "user_claimed", request.state.request_id)
    result = s.Claimed(
        claim_id=claim.id, step=step_view(step), session=s.Session.model_validate(session)
    )
    await remember(db, request, owner.id, str(key), request_digest, result, 200)
    return envelope(request, result)


@router.post("/sessions/{session_id}/steps/{step_id}/skip", response_model=s.Envelope[s.Skipped])
async def skip(
    session_id: UUID,
    step_id: UUID,
    body: s.SkipRequest,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
):
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    step = await owned_step(db, session, str(step_id))
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    check_version(session, body.expected_version)
    if session.state != "awaiting_user_action":
        raise GuideError(409, "invalid_transition", "There is no step waiting on you.")
    await skip_step(db, session, step, request.state.request_id)
    session.last_user_activity_at = m.now()
    # Doc 05 has no awaiting_user_action -> active row: preparing the next
    # instruction is `processing`, the same route a retry or follow-up takes.
    await transition(db, session, "processing", body.reason, request.state.request_id)
    operation = await queue_instruction(db, session, request.state.request_id)
    result = s.Skipped(
        step=step_view(step),
        session=s.Session.model_validate(session),
        next_operation_id=operation.id,
    )
    await remember(db, request, owner.id, str(key), request_digest, result, 200)
    return envelope(request, result)


@router.post(
    "/sessions/{session_id}/steps/{step_id}/verifications",
    response_model=s.Envelope[s.SelfReported],
)
async def verify_step(
    session_id: UUID,
    step_id: UUID,
    body: s.VerifyRequest,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
):
    """Take the user's word for a step, and say so in the record.

    Doc 05 is explicit that this is not a pass: the result is `user_reported`,
    the step keeps its `user_claimed` status, and nothing here can produce a
    verified badge. What it does buy is movement — the next instruction is
    prepared, so a guide with watching off still reaches the end of its plan.
    """
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    step = await owned_step(db, session, str(step_id))
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    check_version(session, body.expected_version)
    if session.state != "awaiting_user_action":
        raise GuideError(409, "invalid_transition", "There is no step waiting on you.")
    if body.evidence_ids:
        # Not silently ignored: a caller that sent evidence asked for an
        # objective check, and returning a self-report instead would be a lie.
        raise GuideError(
            422,
            "evidence_required",
            "Checking a screenshot is not available yet. "
            "You can tell Guider what happened instead.",
        )
    if not body.self_report.strip():
        raise GuideError(
            422, "evidence_required", "Say what happened, or share a screenshot to check."
        )
    claim = await db.scalar(
        select(m.CompletionClaim).where(
            m.CompletionClaim.id == str(body.claim_id),
            m.CompletionClaim.owner_id == owner.id,
            m.CompletionClaim.session_id == session.id,
            m.CompletionClaim.step_id == step.id,
        )
    )
    if claim is None:
        raise not_found()
    if claim.status != "user_claimed":
        raise GuideError(
            409, "invalid_transition", "That confirmation was replaced by a newer one."
        )

    session.last_user_activity_at = m.now()
    await transition(db, session, "verifying", "self_report_requested", request.state.request_id)
    verification = await record_self_report(
        db, session, step, claim, body.self_report.strip(), request.state.request_id
    )
    # Doc 05: a self-report result returns to awaiting_user_action with the step
    # still claimed rather than verified. Preparing the next step is `processing`,
    # the same route skip and retry take.
    await transition(
        db, session, "awaiting_user_action", "self_report_recorded", request.state.request_id
    )
    await transition(db, session, "processing", "next_step_requested", request.state.request_id)
    operation = await queue_instruction(db, session, request.state.request_id)
    result = s.SelfReported(
        verification=s.Verification.model_validate(verification),
        step=step_view(step),
        session=s.Session.model_validate(session),
        next_operation_id=operation.id,
    )
    await remember(db, request, owner.id, str(key), request_digest, result, 200)
    return envelope(request, result)


# A long poll, not a stream. GuidanceEvent.sequence is monotonic per session and
# unique, so a client resumes at its exact cursor after any reconnect. SSE becomes
# a transport swap later without changing this contract.
MAX_WAIT_MS = 30_000
POLL_INTERVAL_SECONDS = 0.4


@router.get("/sessions/{session_id}/events", response_model=s.Envelope[s.EventPage])
async def events(
    session_id: UUID,
    request: Request,
    db: Db,
    owner: Owner,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    wait_ms: Annotated[int, Query(ge=0, le=MAX_WAIT_MS)] = 0,
):
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    rows = await read_events(db, session, after, limit)
    if not rows and wait_ms:
        # Never hold a transaction open while waiting: a reader parked for
        # thirty seconds would block the worker behind it.
        await db.commit()
        deadline = time.monotonic() + wait_ms / 1000
        while not rows and time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            async with request.app.state.sessions() as poll:
                rows = await read_events(poll, session, after, limit)
    return envelope(
        request,
        s.EventPage(
            items=[s.Event.model_validate(row) for row in rows],
            next_after=rows[-1].sequence if rows else after,
        ),
    )


def observation_state(request: Request, session: m.GuideSession) -> s.ObservationState:
    return s.ObservationState(
        active=session.observation_active,
        frames_observed=session.frames_observed,
        observation_calls_remaining=calls_remaining(session),
        consent_version=NOTICE_VERSION,
        session=s.Session.model_validate(session),
    )


@router.post("/sessions/{session_id}/observation", response_model=s.Envelope[s.ObservationState])
async def start_observation(
    session_id: UUID,
    body: s.ObservationConsent,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
):
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    check_version(session, body.expected_version)
    await confirmed_plan(db, session)
    await enable(db, session, body.consent_version, request.state.request_id)
    # Record what this user actually agreed to, not merely that they agreed.
    owner.privacy_notice_version = body.consent_version
    owner.updated_at = m.now()
    await transition(db, session, session.state, "observation_enabled", request.state.request_id)
    result = observation_state(request, session)
    await remember(db, request, owner.id, str(key), request_digest, result, 200)
    return envelope(request, result)


@router.delete("/sessions/{session_id}/observation", response_model=s.Envelope[s.ObservationState])
async def stop_observation(session_id: UUID, request: Request, db: Db, owner: Owner):
    """Always available, never rate limited, and idempotent: a control that stops
    something must not itself be able to fail for being pressed twice."""
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    if session.observation_active:
        await stop_watching(db, session, "user", request.state.request_id)
        await cancel_pending(db, session)
        await transition(
            db, session, session.state, "observation_stopped", request.state.request_id
        )
    return envelope(request, observation_state(request, session))


@router.post("/sessions/{session_id}/replan", status_code=202, response_model=s.Envelope[s.Pending])
async def replan(
    session_id: UUID,
    body: s.ReplanRequest,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
):
    """Ask for a new roadmap for the part that is left.

    What is already done is not up for revision: the replacement carries every
    settled step across untouched, and only what remains is proposed again. The
    result is a draft, like every other plan, because a roadmap the user has not
    seen is not one they agreed to (ADR-010).
    """
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    check_version(session, body.expected_version)
    if session.state != "awaiting_user_action":
        raise GuideError(409, "invalid_transition", "There is no step waiting on you.")
    await confirmed_plan(db, session)
    if await db.scalar(
        select(m.OperationRow.id).where(
            m.OperationRow.session_id == session.id,
            m.OperationRow.status.in_(["queued", "running"]),
        )
    ):
        raise GuideError(409, "operation_in_progress", "An operation is already running.")
    await quota(db, m.OperationRow, owner.id, 10, 60)

    session.last_user_activity_at = m.now()
    session.checkpoint_state = session.state
    # The step being replaced stops being current now: its instruction cannot
    # outlive the plan version it belongs to.
    await retire_instructions(db, session)
    session.current_step_id = None
    await record_event(
        db, session, "session.replan_requested", request.state.request_id, {"reason": body.reason}
    )
    await transition(db, session, "analyzing", "replan", request.state.request_id)
    operation = m.OperationRow(
        id=m.new_id(),
        owner_id=owner.id,
        task_id=session.task_id,
        session_id=session.id,
        kind="replan",
        expected_state_version=session.state_version,
        control_epoch=session.control_epoch,
        request_digest=request_digest,
        deadline_at=m.now() + timedelta(seconds=65),
        expires_at=m.now() + timedelta(hours=24),
    )
    db.add(operation)
    await db.flush()
    await record_event(
        db, session, "operation.started", request.state.request_id, {"operation_id": operation.id}
    )
    result = s.Pending(operation_id=operation.id, session=s.Session.model_validate(session))
    await remember(db, request, owner.id, str(key), request_digest, result, 202)
    return envelope(request, result)


@router.post("/sessions/{session_id}/observe", response_model=s.Envelope[s.ObservationTick])
async def observe(
    session_id: UUID,
    body: s.ObserveRequest,
    request: Request,
    db: Db,
    owner: Owner,
):
    """One observer tick. Synchronous on purpose: the latency budget is about a
    second, and a lost tick is covered by the next one, so this never becomes a
    durable Operation. The frame is held in memory and never stored."""
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    check_version(session, body.expected_version)
    if not session.observation_active:
        raise GuideError(403, "observation_off", "Watching is not switched on for this task.")
    if session.state != "awaiting_user_action":
        raise GuideError(409, "invalid_transition", "There is no step waiting on you.")
    check_budget(session)

    epoch = session.control_epoch
    gate = request.app.state.observation
    gate.admit(session.id, time.monotonic())
    if gate.lock(session.id).locked():
        raise GuideError(409, "observation_in_progress", "Guider is still looking at the last one.")

    instruction = await current_instruction(db, session)
    if instruction is None:
        raise GuideError(409, "invalid_transition", "There is no current instruction to check.")
    step = await owned_step(db, session, instruction.step_id)

    async with gate.lock(session.id):
        pixels = await asyncio.to_thread(prepare_frame, body.image_base64)
        result = vet_observation(
            await asyncio.wait_for(
                request.app.state.observer.observe(
                    ObserveContext(
                        success_criterion=step.success_criterion,
                        expected_result=step.expected_result,
                        application_key=step.application_key,
                    ),
                    pixels,
                ),
                timeout=20,
            )
        )
        # A stop that landed while the provider was busy wins: the epoch moved,
        # so this frame is discarded without spending budget or advancing a step.
        await db.refresh(session)
        if not session.observation_active or session.control_epoch != epoch:
            raise GuideError(409, "observation_stopped", "Watching was switched off.")
        decision = await apply(db, session, step, instruction, result, request.state.request_id)
        if decision == "advance":
            await queue_instruction(db, session, request.state.request_id)

    return envelope(
        request,
        s.ObservationTick(
            decision=decision,
            confidence=result.confidence,
            ui_changed=result.ui_changed,
            anomaly=result.anomaly,
            note=result.note,
            frames_observed=session.frames_observed,
            observation_calls_remaining=max(0, MAX_OBSERVATION_CALLS - session.observation_calls),
            session=s.Session.model_validate(session),
        ),
    )


@router.post("/tasks/{task_id}/screenshots", status_code=201, response_model=s.Envelope[s.Uploaded])
async def upload(
    task_id: UUID,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
    file: Annotated[UploadFile, File()],
    metadata: Annotated[str, Form(max_length=8192)],
):
    task = await owned(db, m.GuideTask, str(task_id), owner.id)
    try:
        meta = s.UploadMetadata.model_validate_json(metadata)
    except ValidationError:
        raise GuideError(422, "validation_failed", "Check the screenshot metadata.") from None
    if meta.source != "manual":
        raise GuideError(403, "capture_not_permitted", "Live observation is not enabled.")
    raw = await file.read(MAX_BYTES + 1)
    await file.close()
    request_digest = digest(meta.model_dump(mode="json"), raw)
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    session = None
    if meta.session_id:
        session = await owned(db, m.GuideSession, str(meta.session_id), owner.id)
        if session.task_id != task.id:
            raise not_found()
        check_version(session, meta.expected_version)
        if session.state not in ANALYSIS_STATES:
            raise GuideError(409, "operation_in_progress", "Wait for the current analysis.")
    replacement = None
    if meta.replaces_screenshot_id:
        replacement = await owned(db, m.ScreenshotRow, str(meta.replaces_screenshot_id), owner.id)
        if replacement.task_id != task.id or replacement.session_id != (
            str(meta.session_id) if meta.session_id else None
        ):
            raise not_found()
        usable(replacement)
    await quota(db, m.ScreenshotRow, owner.id, 30, 60)
    await quota(db, m.ScreenshotRow, owner.id, 100, 3600)
    retained = await db.scalar(
        select(func.count())
        .select_from(m.ScreenshotRow)
        .where(
            m.ScreenshotRow.task_id == task.id,
            m.ScreenshotRow.object_key.is_not(None),
        )
    )
    if retained >= 20 and replacement is None:
        raise GuideError(429, "rate_limited", "Delete an image before uploading another.")
    normalized = await asyncio.to_thread(normalize, raw)
    storage = request.app.state.storage
    object_key = await storage.put(normalized.pixels)
    image = m.ScreenshotRow(
        id=m.new_id(),
        owner_id=owner.id,
        task_id=task.id,
        session_id=session.id if session else None,
        purpose=meta.purpose,
        width=normalized.width,
        height=normalized.height,
        byte_size=len(normalized.pixels),
        object_key=object_key,
        content_hash=normalized.digest,
        captured_at=meta.captured_at,
        expires_at=m.now() + timedelta(hours=24),
        replaces_screenshot_id=replacement.id if replacement else None,
        version=replacement.version + 1 if replacement else 1,
    )
    try:
        db.add(image)
        if replacement:
            await purge_image(db, storage, replacement, request.state.request_id)
        if session:
            session.last_user_activity_at = m.now()
            await transition(db, session, session.state, "manual_upload", request.state.request_id)
            await record_event(
                db,
                session,
                "screenshot.accepted",
                request.state.request_id,
                {"screenshot_id": image.id},
            )
        await db.flush()
        result = s.Uploaded(
            screenshot=s.Screenshot.model_validate(image),
            session=s.Session.model_validate(session) if session else None,
        )
        await remember(db, request, owner.id, str(key), request_digest, result, 201)
        # Commit metadata before returning; failed writes do not leave orphan pixels.
        await db.commit()
    except Exception:
        await storage.delete(object_key)
        raise
    return envelope(request, result)


@router.get("/screenshots/{screenshot_id}/content", response_class=Response)
async def image_content(screenshot_id: UUID, request: Request, db: Db, owner: Owner):
    image = await owned(db, m.ScreenshotRow, str(screenshot_id), owner.id)
    usable(image)
    try:
        pixels = await request.app.state.storage.read(image.object_key)
    except FileNotFoundError:
        raise GuideError(410, "data_deleted", "This image is unavailable.") from None
    return Response(
        pixels,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/screenshots/{screenshot_id}", status_code=202, response_model=s.Envelope[s.DeletionReceipt]
)
async def delete_image(screenshot_id: UUID, request: Request, db: Db, owner: Owner):
    image = await db.scalar(
        select(m.ScreenshotRow).where(
            m.ScreenshotRow.id == str(screenshot_id),
            m.ScreenshotRow.owner_id == owner.id,
        )
    )
    if image is None:
        raise not_found()
    return envelope(
        request,
        await purge_image(
            db,
            request.app.state.storage,
            image,
            request.state.request_id,
        ),
    )


@router.get("/deletions/{deletion_id}", response_model=s.Envelope[s.DeletionReceipt])
async def deletion(deletion_id: UUID, request: Request, db: Db, owner: Owner):
    return envelope(request, await owned(db, m.DeletionJob, str(deletion_id), owner.id))


@router.post("/tasks/{task_id}/analyses", status_code=202, response_model=s.Envelope[s.Pending])
async def analyze(
    task_id: UUID,
    body: s.AnalyzeRequest,
    request: Request,
    db: Db,
    owner: Owner,
    key: Key,
):
    await owned(db, m.GuideTask, str(task_id), owner.id)
    session = await owned(db, m.GuideSession, str(body.session_id), owner.id)
    if session.task_id != str(task_id):
        raise not_found()
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    check_version(session, body.expected_version)
    if session.state not in ANALYSIS_STATES:
        raise GuideError(409, "invalid_transition", "Wait for the current operation to finish.")
    in_flight = await db.scalar(
        select(m.OperationRow.id).where(
            m.OperationRow.session_id == session.id,
            m.OperationRow.status.in_(["queued", "running"]),
        )
    )
    if in_flight:
        raise GuideError(409, "operation_in_progress", "An analysis is already running.")
    if len(set(body.screenshot_ids)) != len(body.screenshot_ids):
        raise GuideError(422, "validation_failed", "Choose distinct screenshots.")
    images = []
    for screenshot_id in body.screenshot_ids:
        image = await owned(db, m.ScreenshotRow, str(screenshot_id), owner.id)
        if image.task_id != str(task_id) or image.session_id not in {None, session.id}:
            raise not_found()
        usable(image)
        images.append(image)
    await quota(db, m.OperationRow, owner.id, 10, 60)
    await quota(db, m.OperationRow, owner.id, 100, 86400)
    session_calls = await db.scalar(
        select(func.count())
        .select_from(m.OperationRow)
        .where(
            m.OperationRow.session_id == session.id,
        )
    )
    if session_calls >= 40:
        raise GuideError(429, "session_budget_exhausted", "This session's analysis budget is used.")
    if session.state not in {"paused", "blocked"}:
        session.checkpoint_state = session.state
        await transition(db, session, "analyzing", "analysis_requested", request.state.request_id)
    else:
        await transition(db, session, session.state, "analysis_requested", request.state.request_id)
    session.last_user_activity_at = m.now()
    operation = m.OperationRow(
        id=m.new_id(),
        owner_id=owner.id,
        task_id=str(task_id),
        session_id=session.id,
        expected_state_version=session.state_version,
        control_epoch=session.control_epoch,
        request_digest=request_digest,
        deadline_at=m.now() + timedelta(seconds=30),
        expires_at=m.now() + timedelta(hours=24),
    )
    db.add(operation)
    await db.flush()
    for image in images:
        db.add(
            m.OperationEvidence(
                operation_id=operation.id,
                screenshot_id=image.id,
                owner_id=owner.id,
                version=image.version,
            )
        )
    await record_event(
        db, session, "operation.started", request.state.request_id, {"operation_id": operation.id}
    )
    result = s.Pending(operation_id=operation.id, session=s.Session.model_validate(session))
    await remember(db, request, owner.id, str(key), request_digest, result, 202)
    return envelope(request, result)


@router.get("/operations/{operation_id}", response_model=s.Envelope[s.Operation])
async def operation(operation_id: UUID, request: Request, db: Db, owner: Owner):
    row = await owned(db, m.OperationRow, str(operation_id), owner.id)
    return envelope(request, await operation_result(db, row))


async def restrict(
    body, request: Request, db: Db, owner: m.User, key: UUID, session_id: UUID, stop: bool
):
    session = await owned(db, m.GuideSession, str(session_id), owner.id)
    request_digest = digest(body.model_dump(mode="json"))
    previous = await replay(db, request, owner.id, str(key), request_digest)
    if previous:
        return envelope(request, previous)
    if session.state not in TERMINAL:
        session.control_epoch += 1
        await cancel_pending(db, session)
        if session.state not in {"paused", "blocked", "analyzing"}:
            session.checkpoint_state = session.state
        if stop:
            session.outcome = "stopped"
            session.ended_at = m.now()
            await transition(db, session, "stopping", body.reason, request.state.request_id)
            await transition(db, session, "completed", body.reason, request.state.request_id)
        else:
            await transition(db, session, "paused", body.reason, request.state.request_id)
    result = s.Session.model_validate(session)
    await remember(db, request, owner.id, str(key), request_digest, result, 200)
    return envelope(request, result)


@router.post("/sessions/{session_id}/pause", response_model=s.Envelope[s.Session])
async def pause(
    session_id: UUID, body: s.PauseRequest, request: Request, db: Db, owner: Owner, key: Key
):
    return await restrict(body, request, db, owner, key, session_id, False)


@router.post("/sessions/{session_id}/stop", response_model=s.Envelope[s.Session])
async def stop(
    session_id: UUID, body: s.StopRequest, request: Request, db: Db, owner: Owner, key: Key
):
    return await restrict(body, request, db, owner, key, session_id, True)
