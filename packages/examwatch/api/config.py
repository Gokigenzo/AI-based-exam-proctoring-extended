from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EXAMWATCH_", env_file=".env", extra="ignore")
    env: str = "development"
    database_url: str = "sqlite:///./data/cloud-demo.sqlite3"
    data_dir: Path = Path("data/cloud")
    allowed_origins: list[str] = ["http://localhost:3000"]
    demo_token: str = ""
    signing_secret: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    max_asset_bytes: int = 50 * 1024 * 1024

    @model_validator(mode="after")
    def production(self):
        if self.env not in ("development", "production", "test"):
            raise ValueError("Unknown environment")
        if self.env == "production":
            if self.demo_token or not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires Postgres and forbids demo auth")
            if not self.supabase_url.startswith("https://") or not self.supabase_key:
                raise ValueError("Production requires Supabase")
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise ValueError("Production CORS origins must use HTTPS")
        if len(self.signing_secret) < 32:
            raise ValueError("Set EXAMWATCH_SIGNING_SECRET to at least 32 random characters")
        return self


@lru_cache
def settings():
    return Settings()
