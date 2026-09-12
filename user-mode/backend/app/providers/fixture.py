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


class FixtureProvider:
    """A test double, not vision: exact fixture recognition, no external transmission."""

    def __init__(self):
        self.fixture_hash = normalize(python_fixture()).digest

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
