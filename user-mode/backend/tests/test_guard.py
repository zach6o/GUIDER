import json
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.guide.guard import NEEDS_REVIEW, restricted_action, vet_analysis, vet_guidance
from app.providers.base import CheckInput, Guidance
from app.providers.openai import OpenAIVision
from app.schemas import Analysis


def guidance(**overrides) -> Guidance:
    return Guidance.model_validate(
        {
            "observation": "The terminal shows a failing command.",
            "next_step": "Read the error text above the prompt.",
            "where": "In the terminal panel.",
            "check_for": "The error text is visible.",
            "question": "",
            "disposition": "guide",
        }
        | overrides
    )


def analysis(**overrides) -> Analysis:
    return Analysis.model_validate(
        {
            "id": uuid4(),
            "screenshot_ids": [uuid4()],
            "observations": [],
            "explanation": "The interpreter cannot find the package.",
            "needs_context": True,
            "context_request": "Which Python environment did you intend to use?",
        }
        | overrides
    )


# --- the shared primitive -------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["Delete the folder", "run sudo apt update", "rm -rf build", "Enter your password", "api key"],
)
def test_restricted_action_catches_unapprovable_directives(text):
    assert restricted_action(text)


@pytest.mark.parametrize(
    "text",
    [
        "A package installed elsewhere may be missing here.",
        "Read the error text.",
        "Open the Settings panel.",
        "",
    ],
)
def test_restricted_action_leaves_ordinary_directives_alone(text):
    assert not restricted_action(text)


# --- role: guide ----------------------------------------------------------


def test_guide_restricted_instruction_is_downgraded_and_stripped():
    result = vet_guidance(guidance(next_step="Delete the node_modules folder."))
    assert result.disposition == "needs_context"
    assert result.question == NEEDS_REVIEW
    assert result.next_step == result.where == result.check_for == ""


@pytest.mark.parametrize("disposition", ["needs_context", "blocked"])
@pytest.mark.parametrize("next_step", ["Read the error text.", "Enter your password."])
def test_guide_non_guide_disposition_never_carries_an_action(disposition, next_step):
    result = vet_guidance(guidance(disposition=disposition, next_step=next_step))
    assert result.disposition == disposition
    assert result.next_step == result.where == result.check_for == ""


def test_guide_safe_instruction_passes_through_untouched():
    original = guidance()
    result = vet_guidance(guidance())
    assert result.disposition == "guide"
    assert result.next_step == original.next_step
    assert result.where == original.where
    assert result.check_for == original.check_for


def test_guide_descriptive_field_may_name_a_risky_operation():
    # An observation describes the screen. Blocking it would reject ordinary reports.
    result = vet_guidance(guidance(observation="A dialog offers to delete the old install."))
    assert result.disposition == "guide"
    assert result.next_step


# --- role: analyze --------------------------------------------------------


def test_analyze_restricted_context_request_is_replaced():
    result = vet_analysis(analysis(context_request="Send the log file to support."))
    assert result.context_request == NEEDS_REVIEW
    assert result.needs_context is True


def test_analyze_explanation_is_descriptive_and_not_pattern_matched():
    text = "The installer failed, so the package was never installed."
    result = vet_analysis(analysis(explanation=text))
    assert result.explanation == text


def test_analyze_ordinary_result_passes_through_untouched():
    original = analysis()
    result = vet_analysis(analysis())
    assert result.context_request == original.context_request
    assert result.explanation == original.explanation


def test_analyze_tolerates_a_result_with_no_context_request():
    result = vet_analysis(analysis(needs_context=False, context_request=None))
    assert result.context_request is None


# --- the ADR-017 invariant ------------------------------------------------


async def test_adapter_cannot_approve_its_own_output():
    """The provider returns a proposal. Only the call site's guard may clear it,
    so a restricted instruction must survive the adapter unchanged."""
    answer = {
        "observation": "A dialog is open.",
        "next_step": "Delete the folder.",
        "where": "In the dialog.",
        "check_for": "The folder is gone.",
        "question": "",
        "disposition": "guide",
    }
    adapter = OpenAIVision(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": json.dumps(answer)}],
                        }
                    ],
                },
            )
        )
    )
    body = CheckInput(
        goal="tidy up", question="", previous_step="", image_base64="AA==", reviewed=True
    )
    proposal = await adapter.analyze(SecretStr("k" * 20), "gpt-4.1-mini", body, b"")

    assert proposal.disposition == "guide"
    assert proposal.next_step == "Delete the folder."

    assert vet_guidance(proposal).disposition == "needs_context"
