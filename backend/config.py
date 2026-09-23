import os
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=env_path)

BASE_DIR = Path(__file__).resolve().parent


def _normalize_db_url(url: str, async_driver: bool) -> str:
    "Normalize a DATABASE_URL to use the correct driver prefix."

    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://"):
        if url.startswith(prefix):
            base = url[len(prefix):]
            break
    else:
        # Unknown prefix — return as-is
        return url

    if async_driver:
        return f"postgresql+asyncpg://{base}"
    return f"postgresql://{base}"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    ENVIRONMENT: str = "development"

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENVIRONMENT == "production"

    JWT_SECRET: str = secrets.token_hex(32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 600

    DATABASE_URL: str = "postgresql://legal_user:legal_password@localhost:5432/legal_db"

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """Async URL for FastAPI request handling (asyncpg driver)."""
        return _normalize_db_url(self.DATABASE_URL, async_driver=True)

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Synchronous URL for Alembic and background threads."""
        return _normalize_db_url(self.DATABASE_URL, async_driver=False)

    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    TRUSTED_PROXIES: str = ""

    @property
    def trusted_proxies(self) -> set[str]:
        return {p.strip() for p in self.TRUSTED_PROXIES.split(",") if p.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


    EMBEDDING_PROVIDER: str = "ollama"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIMENSIONS: int = 768
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = ""
    LLM_NUM_CTX: int = 8192

    @property
    def llm_model_name(self) -> str:
        if self.LLM_MODEL:
            return self.LLM_MODEL
        if self.LLM_PROVIDER.lower() == "ollama":
            return "gemma4:e4b"
        # An alias, not a pinned name: gemini-1.5-flash was retired and 404s.
        return os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    ALLOWED_FILE_EXTENSIONS: set[str] = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}
    MAX_FILE_SIZE_BYTES: int = 25 * 1024 * 1024

    model_config = {"env_file": env_path, "extra": "ignore"}


settings = Settings()

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

if not os.environ.get("JWT_SECRET") and settings.IS_PRODUCTION:
    raise RuntimeError("JWT_SECRET must be set in production")
