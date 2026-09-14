"""Print the observation calibration report for one owner.

    uv run python -m scripts.calibration <owner_id>

D05 asks whether `ADVANCE_AT = 0.85` is the right line. This reads the guidance
events that are still inside their seven-day retention window and prints what
actually happened at each confidence band, including every advance a user
contradicted. It answers no question by itself; it is the instrument that makes
the question answerable with counts instead of opinion.

Deliberately a script and not a route: it is an engineering instrument, and
adding a product surface for it would invite treating a small sample as a
finding.
"""

import asyncio
import sys

from app.config import Settings
from app.database import make_database
from app.guide.calibration import for_owner, render


async def main(owner_id: str) -> int:
    engine, sessions = make_database(Settings())
    try:
        async with sessions() as db:
            report = await for_owner(db, owner_id)
    finally:
        await engine.dispose()
    if report.ticks == 0:
        print(
            "No observation ticks in the retention window for this owner. "
            "Nothing to calibrate against yet."
        )
        return 1
    print(render(report))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
