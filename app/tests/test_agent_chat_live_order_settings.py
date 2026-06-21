from app.services.runtime_setting_service import RuntimeSettingService


def test_agent_chat_live_order_settings_default_safe(db_session):
    settings = RuntimeSettingService().get_settings(db_session)

    assert settings["agent_chat_live_order_enabled"] is False
    assert settings["agent_chat_live_order_kis_enabled"] is False
    assert settings["agent_chat_live_order_buy_enabled"] is False
    assert settings["agent_chat_live_order_sell_enabled"] is False
    assert settings["agent_chat_live_order_requires_confirm"] is True
    assert settings["agent_chat_live_order_confirm_ttl_seconds"] == 120
    assert settings["agent_chat_live_order_max_orders_per_day"] == 1
    assert settings["agent_chat_live_order_max_notional_pct"] == 0.03
    assert settings["agent_chat_live_order_max_notional_krw"] == 50000
    assert settings["agent_chat_live_order_allow_market_order"] is True
    assert settings["agent_chat_live_order_allow_limit_order"] is False
    assert settings["agent_chat_live_order_requires_recent_price"] is True


def test_agent_chat_live_order_settings_can_be_updated(db_session):
    service = RuntimeSettingService()

    settings = service.update_settings(
        db_session,
        {
            "agent_chat_live_order_enabled": True,
            "agent_chat_live_order_kis_enabled": True,
            "agent_chat_live_order_buy_enabled": True,
            "agent_chat_live_order_max_notional_krw": 100000,
        },
    )

    assert settings["agent_chat_live_order_enabled"] is True
    assert settings["agent_chat_live_order_kis_enabled"] is True
    assert settings["agent_chat_live_order_buy_enabled"] is True
    assert settings["agent_chat_live_order_sell_enabled"] is False
    assert settings["agent_chat_live_order_max_notional_krw"] == 100000
