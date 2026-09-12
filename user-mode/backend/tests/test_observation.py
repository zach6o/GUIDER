import base64
import io

import pytest
from PIL import Image
from sqlalchemy import select

from app import models as m
from app.guide.guard import vet_observation
from app.guide.observation import ADVANCE_AT, ASK_AT, MAX_OBSERVATION_CALLS, band
from app.providers.base import ObserveContext, ObserveResult
from app.providers.fixture import FixtureProvider
from app.worker import tick
from tests.test_flow import PREFIX
from tests.test_instructions import act, session_state, started


def frame() -> str:
    image = Image.new("RGB", (320, 200), "#203020")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode()


class StubObserver:
    """Stands in for a vision provider so the bands can be exercised without one."""

    def __init__(self, *results: ObserveResult):
        self.results = list(results)
        self.calls = 0
        self.last: ObserveContext | None = None

    async def observe(self, ctx: ObserveContext, image: bytes) -> ObserveResult:
        self.calls += 1
        self.last = ctx
        assert image, "the frame should reach the provider decoded"
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def verdict(**overrides) -> ObserveResult:
    return ObserveResult.model_validate(
        {
            "step_complete": True, "confidence": 0.95, "app_visible": "terminal",
            "ui_changed": True, "anomaly": "none", "note": "A shell prompt is visible.",
        }
        | overrides
    )


async def watching(harness, *results: ObserveResult):
    """A started session with observation switched on and a stub observer."""
    _, session, current = await started(harness)
    harness.app.state.observer = StubObserver(*(results or (verdict(),)))
    async with harness.app.state.sessions() as db, db.begin():
        row = await db.get(m.GuideSession, session["id"])
        row.observation_active = True
        row.observation_started_at = m.now()
    return await session_state(harness, session["id"]), current


async def observe(harness, session, image=None):
    return await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/observe",
        json={
            "expected_version": session["state_version"],
            "image_base64": image or frame(),
            "admitted_at": m.now().isoformat(),
        },
    )


# --- the bands ------------------------------------------------------------


@pytest.mark.parametrize(
    ("complete", "confidence", "expected"),
    [
        (True, 0.99, "advance"), (True, ADVANCE_AT, "advance"),
        (True, 0.84, "ask"), (True, ASK_AT, "ask"),
        (True, 0.59, "wait"), (True, 0.0, "wait"),
        (False, 1.0, "wait"),  # certainty that nothing happened is still not progress
    ],
)
def test_confidence_decides_and_nothing_else(complete, confidence, expected):
    assert band(verdict(step_complete=complete, confidence=confidence)) == expected


async def test_strong_evidence_advances_and_records_a_verification(harness):
    session, current = await watching(harness)
    body = (await observe(harness, session)).json()["data"]
    assert body["decision"] == "advance"

    async with harness.app.state.sessions() as db:
        result = await db.scalar(select(m.VerificationResult))
        step = await db.get(m.TaskStep, current["step"]["id"])
    assert result.status == "passed"
    assert result.verifier_kind == "visual"
    assert result.observed_confidence == pytest.approx(0.95)
    assert step.status == "verified"
    assert step.verified_at is not None


async def test_advancing_prepares_the_next_instruction(harness):
    session, current = await watching(harness)
    await observe(harness, session)
    await tick(harness.app)
    following = (
        await harness.client.get(PREFIX + f"/sessions/{session['id']}/instruction")
    ).json()["data"]
    assert following["step"]["ordinal"] == current["step"]["ordinal"] + 1


async def test_middle_confidence_asks_instead_of_guessing(harness):
    session, current = await watching(harness, verdict(confidence=0.7))
    body = (await observe(harness, session)).json()["data"]
    assert body["decision"] == "ask"
    assert body["session"]["state"] == "awaiting_user_action"

    async with harness.app.state.sessions() as db:
        assert await db.scalar(select(m.VerificationResult)) is None
        step = await db.get(m.TaskStep, current["step"]["id"])
    assert step.status != "verified"


async def test_weak_evidence_changes_nothing(harness):
    session, _ = await watching(harness, verdict(confidence=0.2))
    body = (await observe(harness, session)).json()["data"]
    assert body["decision"] == "wait"
    assert body["session"]["state"] == "awaiting_user_action"


async def test_every_tick_is_recorded_even_when_it_changes_nothing(harness):
    session, _ = await watching(harness, verdict(confidence=0.1))
    await observe(harness, session)
    async with harness.app.state.sessions() as db:
        event = await db.scalar(
            select(m.GuidanceEvent).where(m.GuidanceEvent.type == "observation.tick")
        )
    assert event.payload["decision"] == "wait"
    assert "image" not in str(event.payload)


# --- budgets --------------------------------------------------------------


async def test_a_ten_minute_session_stays_within_budget(harness):
    """The exit gate. Tier 1 admits at most 12 frames a minute, so ten minutes of
    continuous work cannot spend more than a fraction of the session budget."""
    session, _ = await watching(harness, verdict(confidence=0.1))
    observer = harness.app.state.observer

    admitted = 0
    for _ in range(120):  # 12 a minute for ten minutes, the local ceiling
        current = await session_state(harness, session["id"])
        response = await observe(harness, current)
        if response.status_code == 200:
            admitted += 1
        elif response.json()["error"]["code"] != "rate_limited":
            break

    assert admitted <= 90, admitted
    assert observer.calls == admitted
    final = await session_state(harness, session["id"])
    assert final["state"] == "awaiting_user_action"


async def test_a_spent_budget_falls_back_to_telling_guider_yourself(harness):
    session, current = await watching(harness)
    async with harness.app.state.sessions() as db, db.begin():
        row = await db.get(m.GuideSession, session["id"])
        row.observation_calls = MAX_OBSERVATION_CALLS

    session = await session_state(harness, session["id"])
    response = await observe(harness, session)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "observation_budget_spent"
    assert "tell it when a step is done" in response.json()["error"]["message"]

    # The manual path still works, which is what makes exhaustion a mode.
    claim = await act(harness, session, current["step"]["id"], "claim")
    assert claim.status_code == 200


async def test_the_per_minute_ceiling_is_enforced_on_the_server(harness):
    session, _ = await watching(harness, verdict(confidence=0.1))
    codes = []
    for _ in range(16):
        current = await session_state(harness, session["id"])
        codes.append((await observe(harness, current)).status_code)
    assert 429 in codes
    assert codes.count(200) <= 12


# --- what observation is allowed to do -----------------------------------


async def test_observation_must_be_switched_on(harness):
    _, session, _ = await started(harness)
    harness.app.state.observer = StubObserver(verdict())
    response = await observe(harness, session)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "observation_off"


async def test_nothing_is_observed_when_no_step_is_waiting(harness):
    session, current = await watching(harness)
    await act(harness, session, current["step"]["id"], "skip", reason="not_applicable")
    session = await session_state(harness, session["id"])
    response = await observe(harness, session)
    assert response.status_code == 409


async def test_a_stale_version_is_refused(harness):
    session, _ = await watching(harness)
    response = await observe(harness, {**session, "state_version": 1})
    assert response.status_code == 409


async def test_another_owner_cannot_observe(harness):
    session, _ = await watching(harness)
    from uuid import uuid4

    response = await harness.client.post(
        PREFIX + f"/sessions/{session['id']}/observe",
        json={
            "expected_version": session["state_version"],
            "image_base64": frame(),
            "admitted_at": m.now().isoformat(),
        },
        headers={"Authorization": f"Bearer {harness.token(owner=str(uuid4()))}"},
    )
    assert response.status_code in {401, 404}


async def test_an_unreadable_frame_never_reaches_the_provider(harness):
    session, _ = await watching(harness)
    response = await observe(harness, session, image="not-base64!")
    assert response.status_code == 422
    assert harness.app.state.observer.calls == 0


async def test_no_screenshot_row_is_ever_written(harness):
    session, _ = await watching(harness)
    await observe(harness, session)
    async with harness.app.state.sessions() as db:
        assert (await db.scalars(select(m.ScreenshotRow))).all() == []


async def test_the_observer_sees_the_testable_condition_not_the_prose(harness):
    session, current = await watching(harness)
    await observe(harness, session)
    context = harness.app.state.observer.last
    assert context.success_criterion == current["step"]["success_criterion"]
    assert context.success_criterion != current["step"]["expected_result"]


# --- the guard and the fixture -------------------------------------------


def test_an_observer_has_nowhere_to_put_an_instruction():
    assert "next_step" not in ObserveResult.model_fields
    assert "where" not in ObserveResult.model_fields
    with pytest.raises(ValueError):
        ObserveResult.model_validate({**verdict().model_dump(), "next_step": "Delete it."})


def test_a_note_that_turns_directive_is_cleared_but_the_verdict_survives():
    vetted = vet_observation(verdict(note="Now delete the folder."))
    assert vetted.note == ""
    assert vetted.step_complete is True
    assert vetted.confidence == pytest.approx(0.95)


def test_an_ordinary_note_is_left_alone():
    assert vet_observation(verdict()).note == "A shell prompt is visible."


async def test_the_fixture_observer_reports_no_evidence_rather_than_inventing_it():
    result = await FixtureProvider().observe(
        ObserveContext(success_criterion="A prompt is visible.", expected_result="",
                       application_key="powershell"),
        b"pixels",
    )
    assert result.step_complete is False
    assert result.confidence == 0
    assert band(result) == "wait"
