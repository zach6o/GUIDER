from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GUIDE_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///.local/guide.db"
    storage_path: Path = Path(".local/media")
    supabase_url: str = ""
    # Account-mode provider access, off unless configured. D01 has not selected a
    # provider, so this stays a development switch: with no key the engine runs on
    # the deterministic fixture and reaches no network at all. The id is matched
    # against the registry, and the model name is the adapter's to validate;
    # neither is spelled out here.
    provider_id: str = ""
    provider_api_key: SecretStr | None = None
    provider_model: str = ""
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    def check(self) -> None:
        if self.environment == "production":
            raise RuntimeError(
                "Production is gated: storage encryption, isolated decoding, provider review, "
                "distributed quotas and lifecycle certification are not complete. "
                "Continuous observation additionally requires the approved consent notice "
                "(D06) and the native application gates of ADR-011."
            )
        if self.supabase_url and (
            not self.supabase_url.startswith("https://")
            or not self.supabase_url.endswith(".supabase.co")
        ):
            raise ValueError("Configure an HTTPS Supabase project URL without a trailing slash.")
