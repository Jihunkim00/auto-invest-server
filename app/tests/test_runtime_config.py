from app.config import Settings


def test_config_dir_updates_default_runtime_paths(tmp_path):
    config_dir = tmp_path / "config"

    settings = Settings(
        _env_file=None,
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        alpaca_base_url="https://paper-api.alpaca.markets",
        config_dir=config_dir.as_posix(),
    )

    assert settings.reference_sites_config_path == (
        config_dir / "reference_sites.yaml"
    ).as_posix()
    assert settings.watchlist_us_path == (config_dir / "watchlist_us.yaml").as_posix()
    assert settings.watchlist_kr_path == (config_dir / "watchlist_kr.yaml").as_posix()
    assert settings.market_profiles_config_path == (
        config_dir / "market_profiles.yaml"
    ).as_posix()


def test_openai_market_defaults_are_luna_xhigh(monkeypatch):
    for name in (
        "OPENAI_MODEL",
        "OPENAI_REASONING_EFFORT",
        "AGENT_CHAT_MODEL",
        "AGENT_CHAT_REASONING_EFFORT",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.openai_model == "gpt-6-luna"
    assert settings.openai_reasoning_effort == "xhigh"
