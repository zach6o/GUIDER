"""Deleting a task, a session, or an account, and meaning it.

Until now the only thing a user could delete was a screenshot. Everything else —
the goal they typed, the transcript they pasted, the record of what they were
guided through, the account itself — had no way out.
[09](../../../docs/user-mode-guide/09-security-and-privacy.md) SEC-13 requires
exact deletion semantics, and doc 22 makes closing this the first
phase of V2, because a product that cannot forget should not be given more to
remember.

Three properties this module exists to hold.

**Order, not luck.** Only five foreign keys in the schema cascade. Deleting a
parent row and hoping is how orphans are made, so every table is named here in
dependency order and `tests/test_erasure.py` asserts that nothing owned by the
resource survives. When a table is added and this list is not, that test fails.

**Bytes before rows.** Object storage is deleted before the row that names the
object, because a row is a pointer and losing the pointer first is how bytes are
orphaned forever. A failure between the two leaves a row pointing at nothing,
which is recoverable; the other order is not.

**A receipt survives the thing it describes.** `DeletionJob` is the user's proof,
and doc 08 keeps it readable after the data is gone — for an account, until the
identity itself is removed.
"""

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.guide.engine import TERMINAL, record_event, transition

# Online purge deadline from doc 08: bytes are gone at once, and this is the
# outer bound the receipt promises for derived copies.
PURGE_WITHIN = timedelta(hours=24)


async def receipt_for(
    db: AsyncSession, owner_id: str, scope: str, resource_id: str
) -> m.DeletionJob:
    """One receipt per resource. Deleting twice returns the first one rather than
    claiming a second deletion happened."""
    existing = await db.scalar(
        select(m.DeletionJob).where(
            m.DeletionJob.owner_id == owner_id,
            m.DeletionJob.resource_id == resource_id,
        )
    )
    if existing is not None:
        return existing
    job = m.DeletionJob(
        id=m.new_id(),
        owner_id=owner_id,
        scope=scope,
        resource_id=resource_id,
        status="purging",
        online_purge_due_at=m.now() + PURGE_WITHIN,
    )
    db.add(job)
    await db.flush()
    return job


async def drop_media(db: AsyncSession, storage, images) -> int:
    """Bytes first, then the row. A row pointing at nothing can be cleaned up; a
    byte nothing points at cannot be found again."""
    count = 0
    for image in images:
        if image.object_key:
            await storage.delete(image.object_key)
        image.object_key = None
        image.content_hash = None
        count += 1
    return count


async def tombstone_receipts(db: AsyncSession, owner_id: str, ids: set[str]) -> None:
    """An idempotency replay must not hand back a copy of deleted data.

    The stored response is emptied rather than the record removed, so a client
    retrying with the same key still gets a coherent answer instead of silently
    performing the request a second time.
    """
    if not ids:
        return
    for record in await db.scalars(
        select(m.IdempotencyRecord).where(m.IdempotencyRecord.owner_id == owner_id)
    ):
        blob = str(record.response_ref)
        if any(identifier in blob for identifier in ids):
            record.status = "tombstoned"
            record.response_ref = {}


async def stop_if_running(db: AsyncSession, session: m.GuideSession, request_id: str) -> None:
    """Doc 07: a session is stopped before it is deleted.

    Deleting the rows under a running guide would leave a client pointing at a
    step that no longer exists. Incrementing the epoch is what makes in-flight
    work stop counting wherever it is.
    """
    if session.state in TERMINAL:
        return
    session.control_epoch += 1
    session.observation_active = False
    session.observation_mode = "screenshot_only"
    session.outcome = "stopped"
    session.ended_at = m.now()
    await transition(db, session, "stopping", "deletion_requested", request_id)
    await transition(db, session, "completed", "deleted", request_id)
    await record_event(db, session, "data.deletion_requested", request_id, {"scope": "session"})


async def erase_session(
    db: AsyncSession, storage, session: m.GuideSession, request_id: str
) -> dict[str, int]:
    """Everything belonging to one session, in dependency order.

    The task survives: doc 07 is explicit that deleting a session leaves the task
    in place, because a user removing one attempt has not asked to forget the
    goal.
    """
    owner = session.owner_id
    removed: dict[str, int] = {}
    await stop_if_running(db, session, request_id)

    operations = list(
        await db.scalars(select(m.OperationRow).where(m.OperationRow.session_id == session.id))
    )
    operation_ids = {row.id for row in operations}
    analysis_ids = {row.result_ref for row in operations if row.result_ref}

    images = list(
        await db.scalars(
            select(m.ScreenshotRow).where(
                m.ScreenshotRow.owner_id == owner,
                m.ScreenshotRow.session_id == session.id,
            )
        )
    )
    removed["media"] = await drop_media(db, storage, images)
    image_ids = {row.id for row in images}

    plans = list(
        await db.scalars(
            select(m.TaskPlan).where(
                m.TaskPlan.owner_id == owner, m.TaskPlan.session_id == session.id
            )
        )
    )
    plan_ids = {row.id for row in plans}

    # Children first, parents last. Each statement is scoped by owner as well as
    # by parent, so a bug in one predicate cannot reach another owner's rows.
    async def wipe(model, *where) -> int:
        result = await db.execute(delete(model).where(model.owner_id == owner, *where))
        return result.rowcount or 0

    removed["events"] = await wipe(m.GuidanceEvent, m.GuidanceEvent.session_id == session.id)
    removed["contexts"] = await wipe(
        m.ScreenContextRow, m.ScreenContextRow.session_id == session.id
    )
    removed["verifications"] = await wipe(
        m.VerificationResult, m.VerificationResult.session_id == session.id
    )
    removed["claims"] = await wipe(m.CompletionClaim, m.CompletionClaim.session_id == session.id)
    removed["instructions"] = await wipe(m.Instruction, m.Instruction.session_id == session.id)
    removed["feedback"] = await wipe(m.UserFeedback, m.UserFeedback.session_id == session.id)
    removed["summaries"] = await wipe(m.SessionSummary, m.SessionSummary.session_id == session.id)
    removed["imports"] = await wipe(
        m.ImportedConversation, m.ImportedConversation.session_id == session.id
    )
    if plan_ids:
        removed["steps"] = await wipe(m.TaskStep, m.TaskStep.plan_id.in_(plan_ids))
        removed["plans"] = await wipe(m.TaskPlan, m.TaskPlan.id.in_(plan_ids))
    if operation_ids:
        await db.execute(
            delete(m.OperationEvidence).where(m.OperationEvidence.operation_id.in_(operation_ids))
        )
    if analysis_ids:
        removed["analyses"] = await wipe(m.AnalysisRow, m.AnalysisRow.id.in_(analysis_ids))
    removed["operations"] = await wipe(m.OperationRow, m.OperationRow.session_id == session.id)
    removed["screenshots"] = await wipe(
        m.ScreenshotRow, m.ScreenshotRow.session_id == session.id
    )

    task = await db.get(m.GuideTask, session.task_id)
    if task is not None and task.current_session_id == session.id:
        # Doc 08: a pointer at a purged parent is nulled rather than retained.
        task.current_session_id = None
    await db.execute(
        delete(m.GuideSession).where(
            m.GuideSession.owner_id == owner, m.GuideSession.id == session.id
        )
    )
    # A later session that continued this one keeps its own history and loses the
    # link, rather than pointing at something that no longer exists.
    for successor in await db.scalars(
        select(m.GuideSession).where(
            m.GuideSession.owner_id == owner,
            m.GuideSession.previous_session_id == session.id,
        )
    ):
        successor.previous_session_id = None

    await tombstone_receipts(db, owner, {session.id} | image_ids | operation_ids)
    await db.flush()
    return removed


async def erase_task(
    db: AsyncSession, storage, task: m.GuideTask, request_id: str
) -> dict[str, int]:
    """A task, every session under it, and its task-level media."""
    owner = task.owner_id
    removed: dict[str, int] = {}
    sessions = list(
        await db.scalars(
            select(m.GuideSession).where(
                m.GuideSession.owner_id == owner, m.GuideSession.task_id == task.id
            )
        )
    )
    for session in sessions:
        for key, value in (await erase_session(db, storage, session, request_id)).items():
            removed[key] = removed.get(key, 0) + value
    removed["sessions"] = len(sessions)

    # Screenshots attached to the task rather than to one of its sessions.
    images = list(
        await db.scalars(
            select(m.ScreenshotRow).where(
                m.ScreenshotRow.owner_id == owner, m.ScreenshotRow.task_id == task.id
            )
        )
    )
    removed["media"] = removed.get("media", 0) + await drop_media(db, storage, images)
    image_ids = {row.id for row in images}
    await db.execute(
        delete(m.ScreenshotRow).where(
            m.ScreenshotRow.owner_id == owner, m.ScreenshotRow.task_id == task.id
        )
    )
    await db.execute(
        delete(m.GuideTask).where(m.GuideTask.owner_id == owner, m.GuideTask.id == task.id)
    )
    await tombstone_receipts(db, owner, {task.id} | image_ids)
    await db.flush()
    return removed


async def erase_account(db: AsyncSession, storage, user: m.User, request_id: str) -> dict[str, int]:
    """Every task this owner has, then the identity's own rows.

    The receipt outlives the data on purpose (doc 08): it stays readable until the
    Supabase identity itself is removed, which is a separate, audited step this
    module does not perform.
    """
    removed: dict[str, int] = {}
    tasks = list(await db.scalars(select(m.GuideTask).where(m.GuideTask.owner_id == user.id)))
    for task in tasks:
        for key, value in (await erase_task(db, storage, task, request_id)).items():
            removed[key] = removed.get(key, 0) + value
    removed["tasks"] = len(tasks)

    # Anything owner-scoped that never belonged to a task.
    orphans = list(
        await db.scalars(select(m.ScreenshotRow).where(m.ScreenshotRow.owner_id == user.id))
    )
    removed["media"] = removed.get("media", 0) + await drop_media(db, storage, orphans)
    for model in (m.ScreenshotRow, m.AnalysisRow, m.OperationEvidence, m.OperationRow):
        column = getattr(model, "owner_id", None)
        if column is not None:
            await db.execute(delete(model).where(column == user.id))
    await db.execute(delete(m.IdempotencyRecord).where(m.IdempotencyRecord.owner_id == user.id))
    await db.execute(delete(m.ProviderBinding).where(m.ProviderBinding.owner_id == user.id))
    await db.execute(delete(m.ProviderUsage).where(m.ProviderUsage.owner_id == user.id))

    user.status = "deleting"
    user.deletion_requested_at = m.now()
    # Every token issued before this moment stops being accepted, so the account
    # is unusable from the instant it is requested rather than when purging ends.
    user.auth_revoked_before = m.now()
    await db.flush()
    return removed
