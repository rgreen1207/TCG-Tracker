from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os
 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
 
# Sentinel — placeholder values in .env that mean "not configured"
_PLACEHOLDERS = {
    "your_ebay_app_id", "your_ebay_client_secret",
    "your_pushover_user_key", "your_pushover_app_token",
    "your_pricecharting_api_key", "your_pokemontcg_api_key",
    "change_me_to_a_random_32_byte_hex_string",
    "change_me_to_a_strong_password",
    "", "none", "null",
}
 
 
def _is_set(value: str) -> bool:
    """Return True only if a credential is actually configured."""
    return bool(value) and value.strip().lower() not in _PLACEHOLDERS
 
 
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
 
    # Server
    host: str = "0.0.0.0"
    port: int = 8888
 
    # Security — safe defaults so app boots without .env
    secret_key: str = "dev_secret_change_me"
    admin_password: str = "admin"
    jwt_expire_hours: int = 24
 
    # Pushover — optional
    pushover_user_key: str = ""
    pushover_api_token: str = ""
 
    # eBay Browse API — optional
    ebay_app_id: str = ""
    ebay_client_secret: str = ""
 
    # PriceCharting — optional (paid API key required)
    # https://www.pricecharting.com/api
    pricecharting_api_key: str = ""
 
    # Pokemon TCG API — optional (free key, higher rate limits)
    # https://pokemontcg.io
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
 
    # ── Feature flags (derived from credential state) ──────────
    @property
    def ebay_enabled(self) -> bool:
        return _is_set(self.ebay_app_id) and _is_set(self.ebay_client_secret)
 
    @property
    def pushover_enabled(self) -> bool:
        return _is_set(self.pushover_user_key) and _is_set(self.pushover_api_token)
 
    @property
    def pricecharting_enabled(self) -> bool:
        return _is_set(self.pricecharting_api_key)
 
    @property
    def pokemontcg_enabled(self) -> bool:
        return _is_set(self.pokemontcg_api_key)
 
    @property
    def using_default_secret(self) -> bool:
        return self.secret_key == "dev_secret_change_me"
 
    @property
    def using_default_password(self) -> bool:
        return self.admin_password == "admin"
 
 
settings = Settings()
