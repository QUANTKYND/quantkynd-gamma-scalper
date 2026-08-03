from pydantic import AliasChoices, Field
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
    upstox_access_token_file: str = './data/upstox_token.json'
    upstox_state_signing_secret: str
    front_url: str = Field(
        default='http://localhost:5173',
        validation_alias=AliasChoices('FRONT_URL', 'FRONT_END_URL'),
    )
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
