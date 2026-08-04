from datetime import date

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    app_name: str = "Trading Platform API"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    broker: str
    upstox_client_id: str
    upstox_client_secret: str
    upstox_redirect_uri: str
    upstox_login_url: str = 'https://api.upstox.com/v2/login/authorization/dialog'
    upstox_token_url: str = 'https://api.upstox.com/v2/login/authorization/token'
    upstox_api_version: str = '2.0'
    upstox_api_base_url: str = "https://api.upstox.com"
    upstox_access_token_file: str = './data/upstox_token.json'
    upstox_state_signing_secret: str
    front_url: str = Field(
        default='http://localhost:5173',
        validation_alias=AliasChoices('FRONT_URL', 'FRONT_END_URL'),
    )
    rv_synthetic_seed: int = 17
    rv_synthetic_periods: int = 720
    rv_synthetic_end_date: date = date(2025, 12, 31)
    rv_synthetic_initial_price: float = 24_000.0
    upstox_default_instrument_key: str = "NSE_INDEX|Nifty 50"
    upstox_history_lookback_years: int = 3
    upstox_market_data_mode: str = "ltpc"
    upstox_stream_reconnect_interval_seconds: int = 5
    upstox_stream_max_reconnect_attempts: int = 20
    upstox_max_active_instruments: int = 50
    market_data_stale_after_seconds: int = 5
    market_data_ui_publish_interval_ms: int = 250
    rv_live_recompute_interval_ms: int = 1000
    rv_finalized_snapshot_cache_seconds: int = 900

    @model_validator(mode="after")
    def validate_live_market_data(self) -> "Settings":
        if self.upstox_market_data_mode != "ltpc":
            raise ValueError("UPSTOX_MARKET_DATA_MODE must be ltpc")
        positive_values = (
            self.upstox_history_lookback_years,
            self.upstox_stream_reconnect_interval_seconds,
            self.upstox_stream_max_reconnect_attempts,
            self.upstox_max_active_instruments,
            self.market_data_stale_after_seconds,
            self.market_data_ui_publish_interval_ms,
            self.rv_live_recompute_interval_ms,
            self.rv_finalized_snapshot_cache_seconds,
        )
        if any(value <= 0 for value in positive_values):
            raise ValueError("live market-data counts and durations must be positive")
        if self.market_data_ui_publish_interval_ms > self.rv_live_recompute_interval_ms:
            raise ValueError("MARKET_DATA_UI_PUBLISH_INTERVAL_MS must not exceed RV_LIVE_RECOMPUTE_INTERVAL_MS")
        if not self.upstox_default_instrument_key.strip():
            raise ValueError("UPSTOX_DEFAULT_INSTRUMENT_KEY must not be empty")
        if self.upstox_max_active_instruments > 1000:
            raise ValueError("UPSTOX_MAX_ACTIVE_INSTRUMENTS exceeds the approved LTPC limit")
        return self
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
