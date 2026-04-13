from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Auto Invest Server"
    app_debug: bool = True
    app_env: str = "dev"
    default_symbol: str = "AAPL"

    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_base_url: str

    database_url: str = "sqlite:///./auto_invest.db"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    reference_sites_config_path: str = "config/reference_sites.yaml"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings():
    return Settings()
