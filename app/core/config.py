from functools import lru_cache
import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)


class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    GEMINI_API_KEY: str
    AI_SERVICE_API_KEY: str | None = None  # API key untuk autentikasi dari BE

    model_config = SettingsConfigDict(env_file=str(ENV_PATH), env_file_encoding="utf-8")

    @field_validator("SUPABASE_KEY", mode="after")
    @classmethod
    def _fallback_anon(cls, v, info):
        if v:
            return v
        alt = info.data.get("SUPABASE_ANON_KEY")
        if alt:
            return alt
        raise ValueError("SUPABASE_KEY or SUPABASE_ANON_KEY must be set")


@lru_cache
def get_settings() -> Settings:
    return Settings()