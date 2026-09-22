"""Initialize only the two hosted-personal tables, with no public client grants."""

import asyncio

from sqlalchemy import text

from app.config import Settings
from app.database import make_database
from app.personal_app import validate_hosted
from app.personal_store import PersonalBase


async def main() -> None:
    settings = Settings()
    validate_hosted(settings)
    engine, _ = make_database(settings)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(PersonalBase.metadata.create_all)
            if engine.dialect.name == "postgresql":
                for table in ("personal_keys", "personal_budgets"):
                    await connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
                    await connection.execute(text(f"REVOKE ALL ON {table} FROM PUBLIC"))
                    # Supabase roles need not exist on other PostgreSQL services.
                    for role in ("anon", "authenticated"):
                        exists = await connection.scalar(
                            text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}
                        )
                        if exists:
                            await connection.execute(text(f"REVOKE ALL ON {table} FROM {role}"))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
