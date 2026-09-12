import hashlib
import json
from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app import schemas as s
from app.errors import GuideError, not_found
from app.guide.engine import TERMINAL, record_event, transition


async def current_plan_version(db: AsyncSession, session: m.GuideSession) -> int | None:
    return await db.scalar(
        select(func.max(m.TaskPlan.version)).where(
            m.TaskPlan.owner_id == session.owner_id,
            m.TaskPlan.session_id == session.id,
        )
    )


async def owned(db: AsyncSession, model, resource_id: str, owner: str):
    row = await db.scalar(
        select(model).where(model.id == str(resource_id), model.owner_id == owner)
    )
    if row is None:
        raise not_found()
    if getattr(row, "deleted_at", None):
        raise GuideError(410, "data_deleted", "This item has been deleted.")
    return row


def check_version(session: m.GuideSession, expected: int) -> None:
    if session.expires_at <= m.now():
        raise GuideError(410, "session_expired", "This session has expired.")
    if session.state_version != expected:
        raise GuideError(
            409,
            "stale_version",
            "The session changed. Reload before continuing.",
            details={"current_version": session.state_version},
        )
    if session.state in TERMINAL:
        raise GuideError(409, "invalid_transition", "This session has ended.")


def digest(body: Any, extra: bytes = b"") -> str:
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode() + extra,
    ).hexdigest()


async def replay(
    db: AsyncSession,
    request: Request,
    owner: str,
    key: str,
    request_digest: str,
) -> dict | None:
    row = await db.scalar(
        select(m.IdempotencyRecord).where(
            m.IdempotencyRecord.owner_id == owner,
            m.IdempotencyRecord.key == key,
            m.IdempotencyRecord.method == request.method,
            m.IdempotencyRecord.route == request.url.path,
        )
    )
    if row is None:
        return None
    if row.status == "tombstoned":
        raise GuideError(410, "data_deleted", "The evidence for this request was deleted.")
    if row.expires_at <= m.now():
        await db.delete(row)
        await db.flush()
        return None
    if row.request_digest != request_digest:
        raise GuideError(409, "idempotency_conflict", "Use a new key for a different request.")
    response = dict(row.response_ref)
    if "task_ref" in response:
        task = await owned(db, m.GuideTask, response.pop("task_ref"), owner)
        response["task"] = s.Task.model_validate(task).model_dump(mode="json")
    return response


async def remember(
    db: AsyncSession,
    request: Request,
    owner: str,
    key: str,
    request_digest: str,
    response: s.Schema,
    status: int,
) -> None:
    ref = response.model_dump(mode="json")
    if "task" in ref:
        ref["task_ref"] = ref.pop("task")["id"]
    db.add(
        m.IdempotencyRecord(
            owner_id=owner,
            method=request.method,
            route=request.url.path,
            key=key,
            request_digest=request_digest,
            status_code=status,
            response_ref=ref,
            expires_at=m.now() + timedelta(hours=24),
        )
    )


async def quota(db: AsyncSession, model, owner: str, limit: int, seconds: int) -> None:
    count = await db.scalar(
        select(func.count())
        .select_from(model)
        .where(
            model.owner_id == owner,
            model.created_at > m.now() - timedelta(seconds=seconds),
        )
    )
    if count >= limit:
        raise GuideError(429, "rate_limited", "Please wait before trying again.", retryable=True)


def usable(image: m.ScreenshotRow) -> None:
    if image.status in {"deleted", "deleting", "expired"} or not image.object_key:
        raise GuideError(410, "data_deleted", "This screenshot is no longer available.")
    if image.expires_at <= m.now():
        raise GuideError(410, "media_expired", "This screenshot has expired.")


async def cancel_pending(db: AsyncSession, session: m.GuideSession) -> None:
    pending = await db.scalars(
        select(m.OperationRow).where(
            m.OperationRow.session_id == session.id,
            m.OperationRow.status.in_(["queued", "running"]),
        )
    )
    for operation in pending:
        operation.status = "canceled"
        operation.completed_at = m.now()


async def purge_image(
    db: AsyncSession,
    storage,
    image: m.ScreenshotRow,
    request_id: str,
) -> m.DeletionJob:
    existing = await db.scalar(
        select(m.DeletionJob).where(
            m.DeletionJob.owner_id == image.owner_id,
            m.DeletionJob.resource_id == image.id,
        )
    )
    if existing and existing.status == "purged":
        return existing
    image.status = "deleting"
    operations = list(
        await db.scalars(
            select(m.OperationRow)
            .join(
                m.OperationEvidence,
                m.OperationEvidence.operation_id == m.OperationRow.id,
            )
            .where(m.OperationEvidence.screenshot_id == image.id)
        )
    )
    affected_sessions = set()
    for operation in operations:
        if operation.result_ref:
            await db.execute(delete(m.AnalysisRow).where(m.AnalysisRow.id == operation.result_ref))
        operation.result_ref = None
        operation.status = "canceled"
        operation.error_code = "data_deleted"
        affected_sessions.add(operation.session_id)
    if image.session_id:
        affected_sessions.add(image.session_id)
    for session_id in affected_sessions:
        session = await owned(db, m.GuideSession, session_id, image.owner_id)
        if session.state not in TERMINAL:
            session.control_epoch += 1
            await cancel_pending(db, session)
            target = (
                session.checkpoint_state or "task_created"
                if (session.state == "analyzing")
                else session.state
            )
            await transition(db, session, target, "evidence_deleted", request_id)
            await record_event(
                db, session, "data.deletion_requested", request_id, {"media_id": image.id}
            )
    records = await db.scalars(
        select(m.IdempotencyRecord).where(
            m.IdempotencyRecord.owner_id == image.owner_id,
        )
    )
    operation_ids = {op.id for op in operations}
    for record in records:
        ref = record.response_ref
        if ref.get("screenshot", {}).get("id") == image.id or (
            ref.get("operation_id") in operation_ids
        ):
            record.status = "tombstoned"
            record.response_ref = {}
    if image.object_key:
        await storage.delete(image.object_key)
    image.object_key = None
    image.content_hash = None
    image.status = "deleted"
    image.deleted_at = m.now()
    receipt = existing or m.DeletionJob(
        owner_id=image.owner_id,
        resource_id=image.id,
        online_purge_due_at=m.now() + timedelta(hours=24),
    )
    receipt.status = "purged"
    receipt.completed_at = m.now()
    db.add(receipt)
    await db.flush()
    return receipt


async def read_events(
    db: AsyncSession,
    session: m.GuideSession,
    after: int,
    limit: int,
) -> list[m.GuidanceEvent]:
    """Events after `after`, in order. Expired entries are skipped rather than
    reported, so a client that was away longer than the retention window resumes
    from what still exists instead of stalling on a gap it can never fill."""
    return list(
        await db.scalars(
            select(m.GuidanceEvent)
            .where(
                m.GuidanceEvent.owner_id == session.owner_id,
                m.GuidanceEvent.session_id == session.id,
                m.GuidanceEvent.sequence > after,
                m.GuidanceEvent.expires_at > m.now(),
            )
            .order_by(m.GuidanceEvent.sequence)
            .limit(limit)
        )
    )


async def operation_result(db: AsyncSession, row: m.OperationRow) -> s.Operation:
    result = None
    if row.expires_at <= m.now():
        raise GuideError(410, "data_deleted", "This operation result has expired.")
    # Only the analyze role stores an inline result. A plan operation points at a
    # plan the client fetches separately, so do not look for an AnalysisRow.
    if row.kind == "analyze" and row.result_ref:
        analysis = await db.get(m.AnalysisRow, row.result_ref)
        if analysis and analysis.expires_at > m.now():
            ids = list(
                await db.scalars(
                    select(m.OperationEvidence.screenshot_id).where(
                        m.OperationEvidence.operation_id == row.id,
                    )
                )
            )
            result = s.Analysis(
                id=analysis.id,
                screenshot_ids=ids,
                observations=analysis.observations,
                explanation=analysis.explanation,
                needs_context=analysis.needs_context,
                context_request=analysis.context_request,
            )
        else:
            raise GuideError(410, "media_expired", "The source evidence has expired.")
    return s.Operation(
        id=row.id,
        kind=row.kind,
        status=row.status,
        session_id=row.session_id,
        result=result,
        result_id=row.result_ref,
        error=s.ErrorBody(
            code=row.error_code,
            message="The analysis is unavailable. Try fresh evidence.",
            retryable=row.error_code == "dependency_unavailable",
        )
        if row.error_code
        else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
