from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Auto Invest Server"
    app_debug: bool = True
    app_env: str = "dev"
    default_symbol: str = "AAPL"

    broker_provider: str = "alpaca"

    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_base_url: str

    kis_enabled: bool = False
    kis_env: str = "paper"
    kis_app_key: str | None = None
    kis_app_secret: str | None = None
    kis_account_no: str | None = None
    kis_account_product_code: str = "01"
    kis_hts_id: str | None = None
    kis_base_url: str | None = None
    kis_ws_url: str | None = None
    kis_access_token: str | None = None
    kis_approval_key: str | None = None

    database_url: str = "sqlite:///./auto_invest.db"

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"
    openai_reasoning_effort: str = "medium"

    reference_sites_config_path: str = "config/reference_sites.yaml"
    watchlist_config_path: str = "config/watchlist.yaml"
    market_profiles_config_path: str = "config/market_profiles.yaml"
    max_watchlist_size: int = 50
    watchlist_top_candidates_for_research: int = 5
    watchlist_min_entry_score: int = 65
    watchlist_min_quant_score: int = 60
    watchlist_min_research_score: int = 55
    watchlist_strong_entry_score: int = 75
    watchlist_min_score_gap: int = 3
    watchlist_max_sell_score: int = 25
    watchlist_quant_weight: float = 0.75
    watchlist_research_weight: float = 0.25
    reference_site_cache_ttl_minutes: int = 90
    reference_site_fetch_timeout_seconds: float = 4.0
    reference_site_max_summary_chars: int = 1200

    market_gate_min_confidence: float = 0.55

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings():
    return Settings()
