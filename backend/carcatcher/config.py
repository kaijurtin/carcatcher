"""Application configuration, loaded from environment / .env via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All values are overridable via environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "CarCatcher"
    # SQLite file path. In production this lives on the NFS bind-mount.
    database_path: str = "./data/carcatcher.db"
    # Fixed home point for distance-to-listing sorting: Nominatim's centroid
    # for German postal code 66663 (Merzig), verified live 2026-08-12.
    home_latitude: float = 49.4465237
    home_longitude: float = 6.6269649

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL for the SQLite database."""
        return f"sqlite:///{self.database_path}"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
