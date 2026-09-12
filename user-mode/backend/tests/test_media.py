import io

import pytest
from PIL import Image, PngImagePlugin

from app.errors import GuideError
from app.media import MAX_BYTES, normalize
from app.provider import FixtureProvider


def test_normalization_strips_metadata():
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "secret fixture metadata")
    Image.new("RGB", (40, 40)).save(output, "PNG", pnginfo=metadata)
    normalized = normalize(output.getvalue())
    assert Image.open(io.BytesIO(normalized.pixels)).info == {}


def test_byte_and_dimension_limits():
    with pytest.raises(GuideError) as error:
        normalize(b"0" * (MAX_BYTES + 1))
    assert error.value.status == 413
    output = io.BytesIO()
    Image.new("RGB", (8193, 1)).save(output, "PNG")
    with pytest.raises(GuideError) as error:
        normalize(output.getvalue())
    assert error.value.status == 413


async def test_unknown_image_never_receives_invented_observations():
    from uuid import uuid4

    output = io.BytesIO()
    Image.new("RGB", (30, 30)).save(output, "PNG")
    result = await FixtureProvider().analyze([(str(uuid4()), output.getvalue())])
    assert result.observations == []
    assert result.needs_context
    assert "cannot read" in result.explanation
