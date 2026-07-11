from app.services.agent_chat_tool_registry import AgentChatToolRegistry


def test_tool_registry_exposes_only_safe_auto_executable_tools():
    registry = AgentChatToolRegistry()

    auto_names = registry.tool_names(include_blocked=False)
    all_names = registry.tool_names(include_blocked=True)

    assert "kis_price_lookup" in auto_names
    assert "ops_settings_lookup" in auto_names
    assert "broker_sync_watchdog_status_lookup" in auto_names
    assert "live_order_request_blocker" in all_names
    assert "settings_change_blocker" in all_names
    assert "live_order_request_blocker" not in auto_names
    assert "settings_change_blocker" not in auto_names
    assert "manual_ticket_prefill" not in auto_names

    for tool in registry.list_tools(include_blocked=False):
        assert tool.allowed_auto_execute is True
        assert tool.mutation is False
        assert tool.mode in {"read_only", "analysis_only"}


def test_registry_blocks_invalid_and_live_tools():
    registry = AgentChatToolRegistry()

    assert registry.can_auto_execute("kis_price_lookup") is True
    assert registry.can_auto_execute("live_order_request_blocker") is False
    assert registry.can_auto_execute("settings_change_blocker") is False
    assert registry.can_auto_execute("unknown_submit_tool") is False
    assert registry.is_blocked("unknown_submit_tool") is True
