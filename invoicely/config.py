"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/invoicely.db"

    # Application
    app_base_url: str = "http://localhost:8080"
    trash_retention_days: int = 90

    # Security
    cors_origins: str = "http://localhost:3000,http://localhost:8080"
    api_key: str | None = None  # Optional API key for protection
    mcp_api_key: str | None = None  # API key for remote MCP access (SSE transport)

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
    allowed_logo_extensions: list[str] = [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.logo_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
