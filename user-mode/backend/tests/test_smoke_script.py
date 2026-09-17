"""The smoke script's guardrails, checked without spending anything.

The script itself makes real requests, so it can never be a test. What can be
tested is everything that decides whether a request happens at all: that an
unconfigured machine sends nothing, that a fixture-resolved role is reported as
having sent nothing rather than counted as a pass, and that the frame it would
send is drawn here rather than captured from anyone's screen.
"""

import io

import pytest
from PIL import Image

from app.errors import GuideError
from scripts import smoke_provider


def test_it_sends_nothing_when_no_provider_is_configured(monkeypatch):
    monkeypatch.delenv("GUIDE_PROVIDER_ID", raising=False)
    monkeypatch.delenv("GUIDE_PROVIDER_API_KEY", raising=False)
    monkeypatch.setattr(
        smoke_provider, "default_registry", _fail("a registry was built without a key")
    )
    assert smoke_provider.asyncio.run(smoke_provider.main(["plan"])) == 2


def test_the_frame_is_drawn_here_and_is_a_real_png():
    image = Image.open(io.BytesIO(smoke_provider.synthetic_screen()))
    assert image.format == "PNG"
    assert image.size == (1024, 640)
    # Not a flat rectangle: the observer is asked whether a prompt is visible, and
    # a blank image would make "unreadable" the correct answer and the test
    # meaningless.
    assert len(image.convert("RGB").getcolors(maxcolors=100000)) > 2


def test_the_transcript_carries_the_injection_it_is_meant_to_test():
    assert "ignore all previous instructions" in smoke_provider.TRANSCRIPT.lower()
    assert "docker compose" in smoke_provider.TRANSCRIPT


def test_a_refusal_is_reported_rather_than_raised():
    async def declines():
        raise GuideError(502, "provider_refused", "The provider declined to answer.")

    outcome = smoke_provider.asyncio.run(smoke_provider.timed("observe", declines))
    assert outcome.ok is False
    assert "provider_refused" in outcome.detail
    assert "FAIL" in outcome.line()


def test_an_answer_is_reported_with_its_latency():
    async def answers():
        return "4 steps"

    outcome = smoke_provider.asyncio.run(smoke_provider.timed("plan", answers))
    assert outcome.ok is True
    assert outcome.seconds >= 0
    assert "4 steps" in outcome.line()


def test_every_role_it_offers_has_a_runner():
    # The command line accepts a subset; an id with no runner would fail after
    # the request rather than before it.
    assert set(smoke_provider.RUNNERS) == {
        "analyze", "plan", "instruct", "observe", "observe_context", "import",
    }


def _fail(message: str):
    def refuse(*_args, **_kwargs):
        pytest.fail(message)

    return refuse
