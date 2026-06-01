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
