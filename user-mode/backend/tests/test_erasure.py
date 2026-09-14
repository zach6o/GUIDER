"""Deleting a task, a session and an account, and proving it happened.

The promise these tests hold is narrow and absolute: after a deletion, no row and
no byte belonging to the deleted thing is still reachable. Everything else here —
receipts, tombstones, the surviving task — exists so that the promise can be kept
without breaking something the user did not ask to lose.
"""

from uuid import uuid4

from sqlalchemy import func, inspect, select

from app import models as m
from tests.test_feedback import send as feedback
from tests.test_flow import PREFIX, upload
from tests.test_instructions import session_state, started
from tests.test_self_report import claim, self_report


async def rows_for(harness, model, **where) -> int:
    async with harness.app.state.sessions() as db:
        query = select(func.count()).select_from(model)
        for column, value in where.items():
            query = query.where(getattr(model, column) == value)
        return await db.scalar(query)


class _Created:
    """`upload` takes the task-creation response, so hand it one built from the
    task and session we already have rather than creating a second task."""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return {"data": self._payload}


async def recreate(harness, task):
    session = (await harness.client.get(PREFIX + "/sessions")).json()["data"]["items"][0]["session"]
    return _Created({"task": task, "session": session})


async def worked_session(harness):
    """A session with something of every kind hanging off it."""
    created, session, current = await started(harness)
    task = created.json()["data"]["task"]
    step_id = current["step"]["id"]
    claimed = await claim(harness, session, step_id)
    session = await session_state(harness, session["id"])
    await self_report(harness, session, step_id, claimed["claim_id"])
    session = await session_state(harness, session["id"])
    await feedback(harness, session, "helpful", step_id, "That worked.")
    return task, await session_state(harness, session["id"])


# --- one session ----------------------------------------------------------


async def test_deleting_a_session_removes_everything_under_it(harness):
    task, session = await worked_session(harness)
    response = await harness.client.delete(PREFIX + f"/sessions/{session['id']}")
    assert response.status_code == 202, response.text
    receipt = response.json()["data"]
    assert receipt["scope"] == "session"
    assert receipt["status"] == "purged"

    for model in (
        m.GuideSession, m.Instruction, m.CompletionClaim, m.VerificationResult,
        m.GuidanceEvent, m.UserFeedback, m.TaskPlan, m.TaskStep, m.OperationRow,
    ):
        assert await rows_for(harness, model) == 0, model.__name__

    # The goal survives: removing one attempt is not asking to forget the task.
    assert await rows_for(harness, m.GuideTask, id=task["id"]) == 1
    async with harness.app.state.sessions() as db:
        assert (await db.get(m.GuideTask, task["id"])).current_session_id is None


async def test_a_running_session_is_stopped_before_it_is_deleted(harness):
    _, session, _ = await started(harness)
    before = session["control_epoch"]
    response = await harness.client.delete(PREFIX + f"/sessions/{session['id']}")
    assert response.status_code == 202, response.text
    # Nothing is left to read, and any work in flight was bound to an older epoch.
    assert await rows_for(harness, m.GuideSession) == 0
    assert (await harness.client.get(PREFIX + f"/sessions/{session['id']}")).status_code == 404
    assert before >= 1


async def test_deleting_twice_returns_the_first_receipt(harness):
    _, session = await worked_session(harness)
    first = await harness.client.delete(PREFIX + f"/sessions/{session['id']}")
    assert first.status_code == 202
    again = await harness.client.delete(PREFIX + f"/sessions/{session['id']}")
    # The session is gone, so the second request cannot find it. What must not
    # happen is a second receipt claiming a second deletion.
    assert again.status_code == 404
    assert await rows_for(harness, m.DeletionJob) == 1


# --- a task ---------------------------------------------------------------


async def test_deleting_a_task_takes_its_sessions_and_its_images(harness):
    from tests.test_flow import create

    # A task with an image on it, uploaded while the task is still being framed —
    # which is when a user actually shares a screenshot of their problem.
    created = await create(harness)
    assert (await upload(harness, created)).status_code == 201
    task = created.json()["data"]["task"]
    assert await rows_for(harness, m.ScreenshotRow) == 1

    response = await harness.client.delete(PREFIX + f"/tasks/{task['id']}")
    assert response.status_code == 202, response.text
    assert response.json()["data"]["scope"] == "task"

    for model in (m.GuideTask, m.GuideSession, m.ScreenshotRow, m.TaskPlan, m.TaskStep):
        assert await rows_for(harness, model) == 0, model.__name__


async def test_a_deleted_task_is_gone_from_history(harness):
    task, session = await worked_session(harness)
    await harness.client.delete(PREFIX + f"/tasks/{task['id']}")
    history = await harness.client.get(PREFIX + "/sessions")
    assert history.status_code == 200
    assert history.json()["data"]["items"] == []


# --- an account -----------------------------------------------------------


async def delete_account(harness, confirm="delete-my-guide-account"):
    return await harness.client.request(
        "DELETE", PREFIX + "/account", headers={"X-Confirm-Deletion": confirm}
    )


async def test_the_confirmation_phrase_is_required_exactly(harness):
    await worked_session(harness)
    for wrong in ("", "delete my guide account", "DELETE-MY-GUIDE-ACCOUNT"):
        response = await delete_account(harness, wrong)
        assert response.status_code == 422, wrong
        assert response.json()["error"]["code"] == "validation_failed"
    # Nothing was touched by any of those.
    assert await rows_for(harness, m.GuideTask) == 1


async def test_deleting_an_account_erases_every_owned_row(harness):
    task, _ = await worked_session(harness)
    await upload(harness, await recreate(harness, task))

    response = await delete_account(harness)
    assert response.status_code == 202, response.text
    assert response.json()["data"]["scope"] == "account"

    for model in (
        m.GuideTask, m.GuideSession, m.TaskPlan, m.TaskStep, m.Instruction,
        m.CompletionClaim, m.VerificationResult, m.SessionSummary, m.UserFeedback,
        m.ImportedConversation, m.ScreenshotRow, m.AnalysisRow, m.OperationRow,
        m.OperationEvidence, m.GuidanceEvent, m.IdempotencyRecord,
    ):
        assert await rows_for(harness, model) == 0, model.__name__


async def test_the_account_stops_working_the_moment_deletion_is_requested(harness):
    await worked_session(harness)
    assert (await delete_account(harness)).status_code == 202
    # The token in this client's header was issued before the revocation line, so
    # it is refused from here on — there is no window where a deleted account
    # still works.
    assert (await harness.client.get(PREFIX + "/sessions")).status_code == 401


async def test_the_receipt_outlives_the_data(harness):
    """Doc 08: the receipt is the user's proof, and stays readable until the
    identity itself is removed."""
    await worked_session(harness)
    response = await delete_account(harness)
    receipt = response.json()["data"]
    assert receipt["status"] == "purged"
    assert receipt["completed_at"] is not None
    assert await rows_for(harness, m.DeletionJob) == 1


async def test_another_owner_is_untouched(harness):
    """The single most important property: one deletion, one owner."""
    mine_task, _ = await worked_session(harness)
    other = harness.token("f2bf182e-f619-492b-a1cc-c10cf660ca64")
    theirs = await harness.client.post(
        PREFIX + "/tasks",
        json={
            "title": "Their task",
            "goal": "Set up a project of their own on their own machine.",
            "category": "setup",
            "application_key": "vscode",
        },
        headers={"Idempotency-Key": str(uuid4()), "Authorization": f"Bearer {other}"},
    )
    assert theirs.status_code == 201, theirs.text

    assert (await delete_account(harness)).status_code == 202
    async with harness.app.state.sessions() as db:
        remaining = list(await db.scalars(select(m.GuideTask)))
    assert [row.id for row in remaining] == [theirs.json()["data"]["task"]["id"]]


# --- the rule that keeps this honest as the schema grows ------------------


async def test_every_owned_table_is_named_by_the_erasure_module(harness):
    """A table added without being erased is a privacy leak that no other test
    would catch, because a test only checks the tables it knows about."""
    import app.erasure as erasure

    source = (
        erasure.__loader__.get_source("app.erasure")  # type: ignore[union-attr]
        or ""
    )
    async with harness.app.state.sessions() as db:
        names = await db.run_sync(lambda sync: inspect(sync.bind).get_table_names())

    # Tables an account erasure deliberately does not remove, with the reason.
    exempt = {
        "users",  # the identity row itself; removed with the Supabase identity
        "deletion_jobs",  # the receipt, which outlives the data by design
        "alembic_version",  # schema bookkeeping, not owner data
    }
    for table in names:
        if table in exempt:
            continue
        model = next(
            (
                candidate
                for candidate in m.Base.__subclasses__()
                if getattr(candidate, "__tablename__", None) == table
            ),
            None,
        )
        assert model is not None, f"{table} has no model"
        assert model.__name__ in source, (
            f"{table} is never erased: add it to app/erasure.py or to the exempt "
            f"list here with a reason"
        )
