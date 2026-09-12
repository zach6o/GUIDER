from pathlib import Path

from app.provider import python_fixture

target = Path(__file__).resolve().parents[2] / "web/public/fixtures/python-error.png"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(python_fixture())
print("Created synthetic Python screenshot.")
