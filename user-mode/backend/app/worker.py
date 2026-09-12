import asyncio
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app import models as m
from app.errors import GuideError
from app.guide.guard import vet_analysis
from app.schemas import Analysis
from app.service import change, event, purge_image, usable


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
                await change(
                    db,
                    session,
                    session.checkpoint_state or "task_created",
                    "stale_operation",
                    request_id,
                )
            return
        pending.status = "running"
        pending.attempt_count += 1
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
                await change(
                    db,
                    session,
                    session.checkpoint_state or "task_created",
                    "explanation_ready",
                    request_id,
                )
            else:
                await change(db, session, session.state, "explanation_ready", request_id)
            await event(db, session, "analysis.ready", request_id, {"analysis_id": row.id})
            await event(
                db, session, "operation.completed", request_id, {"operation_id": pending.id}
            )
        except (GuideError, OSError, ValueError, TimeoutError):
            pending.status = "failed"
            pending.error_code = "dependency_unavailable"
            if session.state == "analyzing":
                await change(
                    db,
                    session,
                    session.checkpoint_state or "task_created",
                    "analysis_failed",
                    request_id,
                )
            await event(db, session, "operation.failed", request_id, {"operation_id": pending.id})
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
