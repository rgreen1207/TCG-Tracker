from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8888

    # Security
    secret_key: str = "dev_secret_change_me"
    admin_password: str = "admin"
    jwt_expire_hours: int = 24

    # Pushover
    pushover_user_key: str = ""
    pushover_api_token: str = ""

    # eBay
    ebay_app_id: str = ""
    ebay_client_secret: str = ""

    # PriceCharting
    pricecharting_api_key: str = ""

    # Pokemon TCG
    pokemontcg_api_key: str = ""

    # Polling
    poll_interval_seconds: int = 21600
    notify_cooldown_hours: float = 12.0

    # Filters
    excluded_seller_countries: List[str] = ["CN", "HK"]

    # Paths
    @property
    def db_path(self) -> str:
        return os.path.join(BASE_DIR, "data", "tracker.db")

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


settings = Settings()
