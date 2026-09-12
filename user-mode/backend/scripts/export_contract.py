import json
from pathlib import Path

from app.main import create_app

target = Path(__file__).resolve().parents[2] / "contracts"
target.mkdir(exist_ok=True)
schema = create_app(start_worker=False).openapi()
(target / "openapi.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
(target / "schemas.json").write_text(
    json.dumps(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "components": schema["components"],
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("Exported implemented API contracts.")
