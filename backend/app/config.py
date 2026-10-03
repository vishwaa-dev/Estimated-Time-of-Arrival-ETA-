"""Central configuration.

All values can be overridden by real environment variables (OS env wins over
the `.env` file). Secrets are never exposed through the API layer.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# railcast-ai/backend/app/config.py -> railcast-ai/
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- External APIs (server-side only) ---
    railradar_api_key: str = ""
    weather_api_key: str = ""
    railradar_base_url: str = "https://api.railradar.in/v1"
    weather_base_url: str = "https://api.openweathermap.org/data/2.5"

    # --- Database ---
    # PostgreSQL in production/demo setup; SQLite fallback for zero-install dev.
    database_url: str = "sqlite:///./railcast.db"

    # --- Data mode: LIVE | DEMO | AUTO ---
    data_mode: str = "AUTO"

    # --- Polling / caching / API economy ---
    poll_interval_seconds: int = 300
    weather_cache_ttl_seconds: int = 600
    train_cache_ttl_seconds: int = 180
    railradar_max_calls_per_hour: int = 30

    # --- Prediction tuning ---
    max_recovery_minutes: float = 20.0
    recovery_efficiency: float = 0.5

    # --- Demo simulation ---
    demo_time_scale: int = 60      # 1 real second == 60 simulated seconds
    demo_tick_seconds: int = 45    # backend demo/recalc tick
    demo_train_number: str = "12637"  # the only train that runs the DEMO replay

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def railradar_configured(self) -> bool:
        return bool(self.railradar_api_key)

    @property
    def weather_configured(self) -> bool:
        return bool(self.weather_api_key)


settings = Settings()
