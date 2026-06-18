from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_CONFIG_DIR = "config"


def _config_path(config_dir: str, filename: str) -> str:
    return str(Path(config_dir) / filename).replace("\\", "/")


class Settings(BaseSettings):
    app_name: str = "Auto Invest Server"
    app_debug: bool = True
    app_env: str = "dev"
    app_version: str | None = None
    default_symbol: str = "AAPL"
    default_us_symbol: str = "AAPL"
    default_kr_symbol: str = "005930"
    dry_run: bool = True

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
    kis_real_order_enabled: bool = False
    kis_max_manual_order_qty: int = 1
    kis_max_manual_order_amount_krw: int = 100000
    kis_require_confirmation: bool = True
    kis_confirmation_phrase: str = "I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER"
    kis_scheduler_enabled: bool = False
    kis_scheduler_dry_run: bool = True
    kis_scheduler_allow_real_orders: bool = False
    kr_scheduler_enabled: bool = False
    kr_scheduler_allow_real_orders: bool = False

    database_url: str = "sqlite:///./auto_invest.db"
    log_dir: str = "logs"
    config_dir: str = DEFAULT_CONFIG_DIR

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"
    openai_reasoning_effort: str = "medium"
    agent_chat_model: str = "gpt-5.4-mini"
    agent_chat_reasoning_effort: str = "low"
    agent_chat_temperature: float | None = None
    agent_chat_timeout_seconds: float = 20.0
    agent_chat_fallback_enabled: bool = True

    reference_sites_config_path: str = "config/reference_sites.yaml"
    event_sources_config_path: str = "config/event_sources.yaml"
    watchlist_config_path: str = "config/watchlist.yaml"
    watchlist_us_path: str = "config/watchlist_us.yaml"
    watchlist_kr_path: str = "config/watchlist_kr.yaml"
    market_profiles_config_path: str = "config/market_profiles.yaml"
    market_sessions_config_path: str = "config/market_sessions.yaml"
    market_holidays_config_path: str = "config/market_holidays.yaml"
    kis_token_cache_path: str | None = None
    # KIS read-only rate limiting and account state cache
    kis_read_only_min_interval_seconds: float = 1.0
    kis_read_only_rate_limit_retry_seconds: float = 1.2
    kis_account_state_cache_ttl_seconds: float = 2.0
    kis_account_state_max_stale_seconds: float = 5.0
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

    @model_validator(mode="after")
    def apply_config_dir_defaults(self):
        config_paths = {
            "reference_sites_config_path": "reference_sites.yaml",
            "event_sources_config_path": "event_sources.yaml",
            "watchlist_config_path": "watchlist.yaml",
            "watchlist_us_path": "watchlist_us.yaml",
            "watchlist_kr_path": "watchlist_kr.yaml",
            "market_profiles_config_path": "market_profiles.yaml",
            "market_sessions_config_path": "market_sessions.yaml",
            "market_holidays_config_path": "market_holidays.yaml",
        }
        for field_name, filename in config_paths.items():
            default_value = _config_path(DEFAULT_CONFIG_DIR, filename)
            if getattr(self, field_name) == default_value:
                setattr(self, field_name, _config_path(self.config_dir, filename))
        return self


@lru_cache
def get_settings():
    return Settings()
