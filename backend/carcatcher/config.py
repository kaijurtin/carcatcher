"""Application configuration, loaded from environment / .env via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All values are overridable via environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core ---
    app_name: str = "CarCatcher"
    base_url: str = "http://localhost:8000"
    # SQLite file path. In production this lives on the NFS bind-mount.
    database_path: str = "./data/carcatcher.db"

    # --- Scraping / Firecrawl ---
    firecrawl_base_url: str = "http://localhost:3002"
    firecrawl_api_key: str | None = None
    firecrawl_concurrency: int = 2
    scrape_min_interval_ms: int = 1500
    detail_ttl_hours: int = 24
    search_max_pages: int = 5

    # --- AI / Anthropic ---
    anthropic_api_key: str | None = None
    ai_disabled: bool = False
    ai_monthly_budget_usd: float = 25.0
    haiku_concurrency: int = 5

    # --- AI provider selection (all roles) ---
    # "anthropic" uses the hosted Claude wrapper; "ollama" routes every AI role
    # (normalize/evaluate/translate/recommend) to a local Ollama model.
    ai_provider: str = "anthropic"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:3b"

    # --- Model guides (researched .md, served read-only) ---
    # Empty -> repo-bundled backend/model_guides (see `guides_dir`); override with
    # MODEL_GUIDES_DIR to serve from e.g. the /data volume.
    model_guides_dir: str = ""

    # --- Scoring ---
    min_comps: int = 5
    deal_threshold: float = 0.08
    max_sonnet_evals_per_run: int = 30

    # --- Scheduler / snapshot ---
    scheduler_enabled: bool = True
    # Comma-separated sources crawled each run (must be registered scrapers).
    crawl_sources: str = "kleinanzeigen,autoscout24,mobilede"
    cron_schedule: str = "0 */3 * * *"  # every 3 hours
    cron_secret: str = "change-me"
    run_timeout_minutes: int = 30
    prune_gone_days: int = 14

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL for the SQLite database."""
        return f"sqlite:///{self.database_path}"

    @property
    def crawl_sources_list(self) -> list[str]:
        return [s.strip() for s in self.crawl_sources.split(",") if s.strip()]

    @property
    def bundled_guides_dir(self) -> Path:
        """Repo-bundled guide directory (backend/model_guides), seed source."""
        return Path(__file__).resolve().parent.parent / "model_guides"

    @property
    def guides_dir(self) -> Path:
        """Directory holding model-guide .md files (repo-bundled by default).

        Set MODEL_GUIDES_DIR to serve/write from a persistent volume (e.g. /data),
        which is then seeded from the bundled tree on startup."""
        if self.model_guides_dir:
            return Path(self.model_guides_dir)
        return self.bundled_guides_dir


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
