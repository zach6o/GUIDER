"""Deterministic test double for the `analyze` role. Moved from `app.provider` unchanged.

[12](../../../../docs/user-mode-guide/12-agent-responsibilities.md) requires a
deterministic fixture for each role before provider integration. This adapter is
the development default and the reference used by the provider matrix test.
"""

import hashlib
import io
from uuid import UUID, uuid4

from PIL import Image, ImageDraw

from app.media import normalize
from app.providers.base import (
    InstructionContext,
    PlanContext,
    ProposedInstruction,
    ProposedPlan,
    ProposedStep,
)
from app.schemas import Analysis, BBox, Observation


def python_fixture() -> bytes:
    image = Image.new("RGB", (960, 400), "#18201e")
    draw = ImageDraw.Draw(image)
    draw.text((40, 28), "SYNTHETIC FIXTURE / PowerShell / Python", fill="#a1b5a8")
    draw.text((40, 95), "> python app.py", fill="white")
    draw.text((40, 140), 'File "app.py", line 1, in <module>', fill="white")
    draw.text((40, 175), "import requests", fill="white")
    draw.text((40, 230), "ModuleNotFoundError: No module named 'requests'", fill="#ffc6a7")
    draw.text((40, 340), "Demo image. Contains no personal data.", fill="#a1b5a8")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


# A fixed roadmap for the synthetic Python example. Deterministic on purpose: it
# lets the whole plan/confirm/step loop be exercised with no provider spend and no
# network, which is what 12-agent-responsibilities.md asks for before integration.
FIXTURE_PLAN = [
    {
        "title": "Open the terminal",
        "action": "Open the integrated terminal in your editor.",
        "expected_result": "A shell prompt appears in a panel.",
        "success_criterion": "A command prompt is visible and accepts typing.",
        "fallback": "Use the View menu, then Terminal.",
        "explanation": "The interpreter reports what went wrong in the terminal, not the editor.",
    },
    {
        "title": "Show which interpreter is running",
        "action": "Type `python -c \"import sys; print(sys.executable)\"` and press Enter.",
        "expected_result": "A file path to a python executable is printed.",
        "success_criterion": "A path ending in python or python.exe is visible in the output.",
        "fallback": "If `python` is not found, try `py -c` on Windows or `python3 -c` elsewhere.",
        "explanation": (
            "A package installed for one interpreter is invisible to another. "
            "Knowing which one runs your code is what makes the next step meaningful."
        ),
    },
    {
        "title": "List what that interpreter can see",
        "action": 'Type `python -c "import requests"` and press Enter.',
        "expected_result": "Either nothing is printed, or the same ModuleNotFoundError appears.",
        "success_criterion": "The command finishes and its output is visible.",
        "fallback": "If the prompt does not return, press Ctrl+C and try again.",
        "explanation": (
            "Silence means the package is available to this interpreter. "
            "Repeating the error confirms the package is genuinely missing here."
        ),
    },
]


class FixtureProvider:
    """A test double, not vision: exact fixture recognition, no external transmission.

    Serves the `analyze`, `plan` and `instruct` roles. None reaches a network.
    """

    def __init__(self):
        self.fixture_hash = normalize(python_fixture()).digest

    async def plan(self, ctx: PlanContext) -> ProposedPlan:
        return ProposedPlan(
            assumptions=[
                "This fixed roadmap comes from a development fixture, not from a planner model.",
                f"Written for the {ctx.application_key} workflow on this machine.",
            ],
            steps=[
                ProposedStep(application_key=ctx.application_key, **step) for step in FIXTURE_PLAN
            ],
        )

    async def instruct(self, ctx: InstructionContext) -> ProposedInstruction:
        """Restates the confirmed step as one action. A real writer would use the
        current screen; this one deliberately invents nothing it cannot see."""
        return ProposedInstruction(
            what=ctx.action,
            where=f"In {ctx.application_key.replace('_', ' ')}.",
            why=ctx.explanation,
            confirmation_hint=ctx.expected_result,
            cannot_find_hint=ctx.fallback,
        )

    async def analyze(self, images: list[tuple[str, bytes]]) -> Analysis:
        recognized = len(images) == 1 and (
            hashlib.sha256(images[0][1]).hexdigest() == self.fixture_hash
        )
        return Analysis(
            id=uuid4(),
            screenshot_ids=[UUID(item[0]) for item in images],
            observations=[
                Observation(
                    label="Missing Python package (synthetic fixture)",
                    bbox=BBox(x=0.03, y=0.54, width=0.85, height=0.13),
                    confidence=1,
                )
            ]
            if recognized
            else [],
            explanation=(
                "This synthetic example shows ModuleNotFoundError for requests. "
                "The Python interpreter running app.py cannot find that package. "
                "A package installed in another environment may still be unavailable here. "
                "This explanation comes from a fixed fixture, not a vision model."
            )
            if recognized
            else (
                "The image was saved privately, but the development adapter cannot read "
                "arbitrary screenshots. No vision provider has been configured. "
                "Use the synthetic Python fixture to try the complete example."
            ),
            needs_context=True,
            context_request="Which Python environment did you intend to use?"
            if recognized
            else ("Try the supplied synthetic example. Real image interpretation is not enabled."),
        )
