"""Hosted credentials and durable daily admission; no screenshots or task text."""

from datetime import UTC, date, datetime

from pydantic import SecretStr
from sqlalchemy import JSON, Date, Integer, String, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.crypto import Sealed, open_sealed, root_key, seal
from app.errors import GuideError


class PersonalBase(DeclarativeBase):
    pass


class PersonalKey(PersonalBase):
    __tablename__ = "personal_keys"
    owner: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    sealed: Mapped[dict] = mapped_column(JSON)


class PersonalBudget(PersonalBase):
    __tablename__ = "personal_budgets"
    owner: Mapped[str] = mapped_column(String(36), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)


class AccountKeys:
    available = True

    def __init__(self, sessions, secret: str, daily_calls: int):
        self.sessions = sessions
        self.root = root_key(secret)
        self.daily_calls = daily_calls

    async def providers(self, owner: str) -> list[str]:
        async with self.sessions() as db:
            return list(
                await db.scalars(select(PersonalKey.provider).where(PersonalKey.owner == owner))
            )

    async def save(self, owner: str, provider: str, key: SecretStr) -> None:
        sealed = seal(key, self.root, f"{owner}:{provider}").as_dict()
        async with self.sessions() as db, db.begin():
            insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
            await db.execute(
                insert(PersonalKey)
                .values(owner=owner, provider=provider, sealed=sealed)
                .on_conflict_do_update(
                    index_elements=["owner", "provider"], set_={"sealed": sealed}
                )
            )

    async def read(self, owner: str, provider: str) -> SecretStr:
        async with self.sessions() as db:
            row = await db.get(PersonalKey, (owner, provider))
            if row is None:
                raise GuideError(404, "saved_key_unavailable", "Enter and save your API key again.")
            return open_sealed(Sealed(**row.sealed), self.root, f"{owner}:{provider}")

    async def forget(self, owner: str, provider: str) -> None:
        async with self.sessions() as db, db.begin():
            await db.execute(
                delete(PersonalKey).where(
                    PersonalKey.owner == owner, PersonalKey.provider == provider
                )
            )

    async def admit(self, owner: str) -> None:
        """Reserve before calling a provider; failed/canceled calls still consume quota."""
        today = datetime.now(UTC).date()
        async with self.sessions() as db, db.begin():
            insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
            statement = insert(PersonalBudget).values(owner=owner, day=today, calls=1)
            statement = statement.on_conflict_do_update(
                index_elements=["owner", "day"],
                set_={"calls": PersonalBudget.calls + 1},
                where=PersonalBudget.calls < self.daily_calls,
            ).returning(PersonalBudget.calls)
            if await db.scalar(statement) is None:
                raise GuideError(
                    429, "provider_budget_spent", "Your daily AI request limit is reached."
                )
            await db.execute(delete(PersonalBudget).where(PersonalBudget.day < today))
