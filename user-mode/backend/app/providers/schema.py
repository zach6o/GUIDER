"""One internal JSON Schema per role, rendered into each provider's dialect.

Adapters MUST obtain their response-format block here rather than hand-building
one, so the conservative keyword subset stays identical across providers.
Dialects land with the adapter that uses them; an unimplemented dialect raises
rather than silently emitting a format the provider will ignore.
"""

from typing import Any

from pydantic import BaseModel

from app.providers.base import StructuredOutput

# Structured Outputs implementations reject or ignore these; dropping them keeps
# one schema usable everywhere. Bounds stay enforced by Pydantic on the way in.
# Keep this list minimal: widen it only with evidence from a specific provider.
UNSUPPORTED_KEYWORDS = ("minLength", "maxLength")


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The model's JSON Schema, reduced to the broadly supported subset."""
    schema = model.model_json_schema()
    for prop in schema.get("properties", {}).values():
        for keyword in UNSUPPORTED_KEYWORDS:
            prop.pop(keyword, None)
    return schema


def render(model: type[BaseModel], name: str, dialect: StructuredOutput) -> dict[str, Any]:
    """The provider-shaped response-format block for `model`."""
    if dialect == "json_schema":
        return {
            "format": {
                "type": "json_schema",
                "name": name,
                "strict": True,
                "schema": strict_schema(model),
            }
        }
    raise NotImplementedError(
        f"Structured-output dialect {dialect!r} has no renderer yet; "
        "add it with the adapter that needs it."
    )
