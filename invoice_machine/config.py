"""Application configuration using Pydantic Settings."""

import logging
import shutil
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/invoice_machine.db"

    # Application
    app_base_url: str = "http://localhost:8080"
    trash_retention_days: int = 90

    # Security
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.logo_dir.mkdir(parents=True, exist_ok=True)

        # Gracefully migrate database from old name (invoicely.db) to new name (invoice_machine.db)
        self._migrate_database_if_needed()

    def _migrate_database_if_needed(self) -> None:
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
            logger.info(f"Migrating database from {old_db_path} to {new_db_path}")
            try:
                shutil.move(str(old_db_path), str(new_db_path))
                logger.info("Database migration completed successfully")
            except Exception as e:
                logger.error(f"Database migration failed: {e}")
                # Don't raise - let the app continue with whatever DB exists

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
