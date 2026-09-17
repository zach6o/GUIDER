from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.models import ProviderUsage


def make_database(settings: Settings):
    engine = create_async_engine(settings.database_url)
    if settings.database_url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def sqlite_fk(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def database(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        try:
            async with session.begin():
                yield session
        except Exception:
            # A rejected/failed answer can still be a billed provider call.
            # Preserve content-free accounting after rolling back task changes.
            attempts = session.info.pop("provider_attempts", [])
            if attempts:
                async with request.app.state.sessions() as accounting, accounting.begin():
                    accounting.add_all(ProviderUsage(**attempt) for attempt in attempts)
            raise
