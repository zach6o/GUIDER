import asyncio
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app import models as m
from app.worker import tick
from tests.test_flow import PREFIX, create
from tests.test_planning import request_plan


async def events(harness, session_id, **params):
    query = "&".join(f"{name}={value}" for name, value in params.items())
    return await harness.client.get(
        PREFIX + f"/sessions/{session_id}/events" + (f"?{query}" if query else "")
    )


async def busy_session(harness):
    """A session with a handful of events already recorded."""
    created = await create(harness)
    session_id = created.json()["data"]["session"]["id"]
    await request_plan(harness, created)
    await tick(harness.app)
    return created, session_id


async def test_events_arrive_in_order_from_the_start(harness):
    _, session_id = await busy_session(harness)
    body = (await events(harness, session_id)).json()["data"]
    sequences = [event["sequence"] for event in body["items"]]
    assert sequences == sorted(sequences)
    assert sequences[0] == 1
    assert body["next_after"] == sequences[-1]
    assert body["items"][0]["type"] == "task.created"


async def test_a_cursor_returns_only_what_follows_it(harness):
    _, session_id = await busy_session(harness)
    everything = (await events(harness, session_id)).json()["data"]["items"]
    cursor = everything[2]["sequence"]

    rest = (await events(harness, session_id, after=cursor)).json()["data"]["items"]
    assert [event["sequence"] for event in rest] == [
        event["sequence"] for event in everything if event["sequence"] > cursor
    ]


async def test_a_forced_reconnect_resumes_at_the_exact_cursor(harness):
    """The exit gate: page through, drop the connection, resume, and end up with
    every event exactly once and in order."""
    _, session_id = await busy_session(harness)
    total = (await events(harness, session_id, limit=200)).json()["data"]["items"]
    assert len(total) > 4

    collected: list[int] = []
    cursor = 0
    for _ in range(len(total)):
        page = (await events(harness, session_id, after=cursor, limit=2)).json()["data"]
        if not page["items"]:
            break
        collected.extend(event["sequence"] for event in page["items"])
        cursor = page["next_after"]
        # Simulate the connection dropping between pages: the client keeps only
        # its cursor and asks again from there.
        await harness.client.get(PREFIX + f"/sessions/{session_id}")

    assert collected == [event["sequence"] for event in total]
    assert len(collected) == len(set(collected))  # no duplicates
    assert (await events(harness, session_id, after=cursor)).json()["data"]["items"] == []


async def test_the_cursor_holds_when_there_is_nothing_new(harness):
    _, session_id = await busy_session(harness)
    page = (await events(harness, session_id)).json()["data"]
    again = (await events(harness, session_id, after=page["next_after"])).json()["data"]
    assert again["items"] == []
    assert again["next_after"] == page["next_after"]


async def test_a_long_poll_returns_as_soon_as_an_event_arrives(harness):
    created, session_id = await busy_session(harness)
    cursor = (await events(harness, session_id)).json()["data"]["next_after"]

    waiting = asyncio.create_task(events(harness, session_id, after=cursor, wait_ms=8000))
    await asyncio.sleep(0.2)
    assert not waiting.done()  # nothing yet, so the request is parked

    await request_plan(harness, created)
    body = (await waiting).json()["data"]
    assert body["items"]
    assert body["items"][0]["sequence"] > cursor


async def test_a_long_poll_gives_up_quietly(harness):
    _, session_id = await busy_session(harness)
    cursor = (await events(harness, session_id)).json()["data"]["next_after"]
    body = (await events(harness, session_id, after=cursor, wait_ms=700)).json()["data"]
    assert body["items"] == []
    assert body["next_after"] == cursor


async def test_waiting_does_not_block_other_work(harness):
    """A parked reader must not hold a transaction: the worker has to keep running."""
    created, session_id = await busy_session(harness)
    cursor = (await events(harness, session_id)).json()["data"]["next_after"]
    waiting = asyncio.create_task(events(harness, session_id, after=cursor, wait_ms=6000))
    await asyncio.sleep(0.2)

    await request_plan(harness, created)
    await tick(harness.app)  # would deadlock if the reader held its transaction
    assert (await waiting).status_code == 200

    async with harness.app.state.sessions() as db:
        plans = list(await db.scalars(select(m.TaskPlan)))
    assert len(plans) == 2


async def test_expired_events_are_skipped_rather_than_leaving_a_gap(harness):
    _, session_id = await busy_session(harness)
    async with harness.app.state.sessions() as db, db.begin():
        first = await db.scalar(
            select(m.GuidanceEvent).order_by(m.GuidanceEvent.sequence).limit(1)
        )
        first.expires_at = m.now() - timedelta(seconds=1)
        gone = first.sequence

    sequences = [
        event["sequence"] for event in (await events(harness, session_id)).json()["data"]["items"]
    ]
    assert gone not in sequences
    assert sequences == sorted(sequences)


async def test_another_owner_cannot_read_the_history(harness):
    _, session_id = await busy_session(harness)
    response = await harness.client.get(
        PREFIX + f"/sessions/{session_id}/events",
        headers={"Authorization": f"Bearer {harness.token(owner=str(uuid4()))}"},
    )
    assert response.status_code in {401, 404}


async def test_the_wait_is_capped(harness):
    _, session_id = await busy_session(harness)
    response = await events(harness, session_id, wait_ms=120_000)
    assert response.status_code == 422


async def test_payloads_stay_content_free(harness):
    _, session_id = await busy_session(harness)
    body = (await events(harness, session_id)).json()["data"]
    goal = "Why won't Python run?"
    assert all(goal not in str(event["payload"]) for event in body["items"])
