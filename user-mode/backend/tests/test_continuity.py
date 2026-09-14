"""Finding a task again, and taking a copy of it.

History is where a user goes when they half-remember something. The filters exist
for that, and the export exists so a record they can read is theirs rather than
only ours. Both have one rule in common, which most of these tests are about:
what Guider *saw* never leaves through either of them.
"""

from uuid import uuid4

from tests.test_context import seen, tick, watching_context
from tests.test_flow import PREFIX, create
from tests.test_instructions import session_state, started
from tests.test_self_report import advance, claim, self_report


async def history(harness, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    path = PREFIX + (f"/sessions?{query}" if query else "/sessions")
    response = await harness.client.get(path)
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


# --- finding it again -----------------------------------------------------


async def test_searching_matches_the_words_the_user_wrote(harness):
    await create(harness, goal="Why won't my Python file run?")
    await create(harness, goal="Set up Docker Desktop on this laptop and check it works.")

    assert len(await history(harness)) == 2
    docker = await history(harness, q="docker")
    assert len(docker) == 1
    assert "Docker" in docker[0]["task_title"]


async def test_searching_ignores_case_and_matches_the_goal_as_well_as_the_title(harness):
    await create(harness, goal="Set up Docker Desktop on this laptop and check it works.")
    assert len(await history(harness, q="LAPTOP")) == 1


async def test_a_search_that_matches_nothing_is_empty_rather_than_everything(harness):
    await create(harness, goal="Why won't my Python file run?")
    assert await history(harness, q="kubernetes") == []


async def test_history_can_be_narrowed_to_how_a_task_ended(harness):
    _, session, _ = await started(harness)
    while await advance(harness, session["id"]):
        pass
    session = await session_state(harness, session["id"])
    finished = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/completion",
        json={"expected_version": session["state_version"], "outcome": "user_reported"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert finished.status_code == 200, finished.text

    assert len(await history(harness, outcome="user_reported")) == 1
    assert await history(harness, outcome="achieved") == []


async def test_what_guider_saw_is_not_searchable(harness):
    """A search box over descriptions of somebody's desktop is a different
    product. Only the user's own words are matched."""
    session, _ = await watching_context(harness, seen(screen="a download page"))
    await tick(harness, session)
    assert await history(harness, q="download page") == []


# --- taking a copy --------------------------------------------------------


async def test_an_export_carries_the_record_and_not_the_screen(harness):
    session, current = await watching_context(harness, seen(screen="a private banking page"))
    await tick(harness, session)
    session = await session_state(harness, session["id"])

    response = await harness.client.get(PREFIX + f"/sessions/{session['id']}/export")
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["goal"]
    assert body["steps"]
    # The whole point: a record the user can forward carries no description of
    # what was on their screen.
    blob = str(body).lower()
    assert "banking" not in blob
    assert "download page" not in blob
    # Counts, not contents.
    assert body["frames_observed"] >= 1


async def test_an_export_says_how_each_step_was_settled(harness):
    _, session, current = await started(harness)
    step_id = current["step"]["id"]
    claimed = await claim(harness, session, step_id)
    session = await session_state(harness, session["id"])
    await self_report(harness, session, step_id, claimed["claim_id"])

    body = (await harness.client.get(PREFIX + f"/sessions/{session['id']}/export")).json()["data"]
    settled = {row["title"]: row["settled_by"] for row in body["steps"]}
    # The distinction the whole record exists to keep, carried into the copy the
    # user takes away.
    assert settled[current["step"]["title"]] == "you reported this"
    assert "not started" in settled.values()
    assert all(row["verified_at"] is None for row in body["steps"])


async def test_another_owner_cannot_export_this_session(harness):
    _, session, _ = await started(harness)
    other = harness.token("f2bf182e-f619-492b-a1cc-c10cf660ca64")
    response = await harness.client.get(
        PREFIX + f"/sessions/{session['id']}/export",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert response.status_code == 404
