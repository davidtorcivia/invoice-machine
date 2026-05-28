"""Application configuration using Pydantic Settings."""

import logging
import shutil
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings.

    NOTE: This is a pure value object. It must not perform filesystem side
    effects (directory creation, legacy DB rename) in ``__init__`` because it is
    constructed lazily via ``get_settings()`` (``@lru_cache``) at import time.
    Use ``prepare_runtime()`` explicitly during startup instead.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Tolerate env/.env keys that aren't declared here (e.g. PORT,
        # INVOICE_MACHINE_ENCRYPTION_KEY which are consumed elsewhere). Without
        # this, a production .env makes the whole app fail to import.
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/invoice_machine.db"

    # Application
    port: int = 8080
    app_base_url: str = "http://localhost:8080"
    trash_retention_days: int = 90

    # Security
    # Declared for documentation/validation only. The actual key is read from
    # os.environ directly in invoice_machine.crypto (so it must be a real
    # process environment variable, not just a .env entry, in production).
    invoice_machine_encryption_key: str | None = None
    cors_origins: str = "http://localhost:3000,http://localhost:8080"
    secure_cookies: bool = False  # Set to True when using HTTPS in production
    environment: str = "development"  # development, staging, production

    # Paths
    data_dir: Path = Path("./data")
    pdf_dir: Path = Path("./data/pdfs")
    logo_dir: Path = Path("./data/logos")

    # Invoice defaults
    default_payment_terms_days: int = 30
    default_currency_code: str = "USD"
    default_accent_color: str = "#16a34a"

    # File upload limits
    max_logo_size_mb: int = 5
    # Note: SVG is excluded due to XSS security risks (can contain embedded JavaScript)
    allowed_logo_extensions: list[str] = [".jpg", ".jpeg", ".png", ".gif", ".webp"]

    def ensure_runtime_dirs(self) -> None:
        """Create the data/pdf/logo directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.logo_dir.mkdir(parents=True, exist_ok=True)

    def migrate_legacy_database(self) -> None:
        """
        Migrate database from old name (invoicely.db) to new name (invoice_machine.db).

        This ensures existing production installations continue to work seamlessly
        after the rename. The migration only happens if:
        1. The old database file exists (invoicely.db)
        2. The new database file does NOT exist (invoice_machine.db)
        """
        old_db_path = self.data_dir / "invoicely.db"
        new_db_path = self.data_dir / "invoice_machine.db"

        if old_db_path.exists() and not new_db_path.exists():
            logger.info("Migrating database from %s to %s", old_db_path, new_db_path)
            try:
                shutil.move(str(old_db_path), str(new_db_path))
                logger.info("Database migration completed successfully")
            except Exception as e:
                logger.error("Database migration failed: %s", e)
                # Don't raise - let the app continue with whatever DB exists

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def prepare_runtime() -> Settings:
    """Perform one-time filesystem bootstrap (dirs + legacy DB rename).

    Idempotent. Call this once at process startup (web lifespan / MCP server /
    entrypoint) before touching the database or writing files.
    """
    settings = get_settings()
    settings.ensure_runtime_dirs()
    settings.migrate_legacy_database()
    return settings
