from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Database (defaults to a local SQLite file, no Postgres needed) ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./darijadoc.db"

    # --- Redis (optional locally; features that need it degrade gracefully) ---
    REDIS_URL: str | None = None

    # --- Auth ---
    JWT_SECRET: str = "dev-only-insecure-secret-change-me"
    JWT_EXPIRES_DAYS: int = 30

    # --- Credential encryption ---
    CREDENTIALS_ENCRYPTION_KEY: str | None = None

    # --- OpenAI ---
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TTS_MODEL: str = "tts-1"
    OPENAI_TTS_VOICE: str = "alloy"
    OPENAI_STT_MODEL: str = "whisper-1"

    # --- OCR (LLMWhisperer) ---
    LLMWHISPERER_BASE_URL: str = "https://llmwhisperer-api.us-central.unstract.com/api/v2"
    LLMWHISPERER_API_KEY: str | None = None

    @property
    def openai_configured(self) -> bool:
        return bool(self.OPENAI_API_KEY)

    @property
    def llmwhisperer_configured(self) -> bool:
        return bool(self.LLMWHISPERER_API_KEY)

    # --- lowercase aliases -------------------------------------------------
    # handles/deep_analyzed.py (OCR + RAG module) reads settings via
    # lowercase attribute names (cfg.openai_api_key, cfg.llmwhisperer_base_url,
    # ...). Keep those as thin aliases instead of renaming the canonical
    # UPPER_CASE fields used everywhere else.
    @property
    def openai_api_key(self) -> str | None:
        return self.OPENAI_API_KEY

    @property
    def openai_model(self) -> str:
        return self.OPENAI_MODEL

    @property
    def llmwhisperer_api_key(self) -> str | None:
        return self.LLMWHISPERER_API_KEY

    @property
    def llmwhisperer_base_url(self) -> str:
        return self.LLMWHISPERER_BASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
