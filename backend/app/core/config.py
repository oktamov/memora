"""Application settings, loaded from the environment (see `.env.example`)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Nothing is read from the environment elsewhere."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Core ---
    DATABASE_URL: str = "postgresql+asyncpg://memora:memora@localhost:5432/memora"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = "dev-insecure-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_TTL_HOURS: int = 24

    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    TELEGRAM_WEBHOOK_PATH_SECRET: str = "dev-path-secret"
    MINI_APP_URL: str = "https://localhost"
    INIT_DATA_MAX_AGE_SECONDS: int = 86_400  # SPEC §7 step 6

    # --- Providers ---
    AZURE_TRANSLATOR_KEY: str = ""
    AZURE_TRANSLATOR_REGION: str = ""
    AZURE_TRANSLATOR_ENDPOINT: str = "https://api.cognitive.microsofttranslator.com"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_ENDPOINT: str = "https://generativelanguage.googleapis.com/v1beta"
    FREE_DICTIONARY_ENDPOINT: str = "https://api.dictionaryapi.dev/api/v2/entries"

    PROVIDER_TIMEOUT_SECONDS: float = 4.0  # SPEC §6: >4s falls through the chain

    # --- Behaviour / abuse controls (SPEC §8) ---
    UZ_PREFER_LLM: bool = True
    DAILY_PROVIDER_BUDGET: int = 5_000
    LOOKUP_MAX_CHARS: int = 64
    LOOKUP_MAX_TOKENS: int = 4
    LOOKUP_RATE_PER_MINUTE: int = 20
    AUTH_RATE_PER_MINUTE_PER_IP: int = 60
    NEW_ACCOUNT_LOOKUP_QUOTA: int = 30
    NEW_ACCOUNT_WINDOW_HOURS: int = 24
    REDIS_LOOKUP_TTL_SECONDS: int = 86_400  # SPEC §6: Redis TTL 24h

    # --- Defaults for new users (SPEC §5) ---
    DEFAULT_NATIVE_LANG: str = "uz"
    DEFAULT_UI_LANG: str = "uz"
    DEFAULT_TIMEZONE: str = "Asia/Tashkent"

    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def bot_enabled(self) -> bool:
        """The bot only mounts when a token is configured (see BLOCKERS.md)."""
        return bool(self.TELEGRAM_BOT_TOKEN)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton so `Settings()` is parsed once per process."""
    return Settings()


settings = get_settings()
