from __future__ import annotations

from types import SimpleNamespace

from app.services.agent_command_parser_service import AgentCommandParserService


def _settings(openai_api_key=None):
    return SimpleNamespace(
        openai_api_key=openai_api_key,
        openai_model="test-agent-model",
        openai_reasoning_effort="low",
    )


def _service(openai_client=None):
    return AgentCommandParserService(
        openai_client=openai_client,
        settings=_settings(openai_api_key="test-key" if openai_client else None),
    )


def _context():
    return {
        "default_market": "KR",
        "default_provider": "kis",
        "timezone": "Asia/Seoul",
    }


def _assert_no_execution_flags(response):
    safety = response["safety"]
    assert safety["execution_blocked_in_pr56"] is True
    assert safety["real_order_submitted"] is False
    assert safety["broker_submit_called"] is False
    assert safety["manual_submit_called"] is False
    assert safety["setting_changed"] is False
    assert safety["scheduler_changed"] is False
    command_safety = response["command"]["safety"]
    assert command_safety == safety


def test_korean_single_symbol_analysis_falls_back_without_api_key(db_session):
    response = _service().parse(
        db_session,
        message="오늘 삼성전자 살만한지 봐줘",
        context=_context(),
    )

    command = response["command"]
    assert response["parser_status"] == "fallback"
    assert command["command_type"] == "RUN_SINGLE_SYMBOL_ANALYSIS"
    assert command["domain"] == "analysis"
    assert command["market"] == "KR"
    assert command["provider"] == "kis"
    assert command["symbol"] == "005930"
    assert command["requires_auth"] is False
    assert command["execution_policy"]["allow_live_order"] is False
    _assert_no_execution_flags(response)


def test_korean_conditional_buy_schedule_requires_auth_and_stays_blocked(db_session):
    response = _service().parse(
        db_session,
        message="내일 10시에 삼성전자 조건 맞으면 3만원 사줘",
        context=_context(),
    )

    command = response["command"]
    assert command["command_type"] == "CREATE_AGENT_PLAN"
    assert command["intent"] == "conditional_buy_schedule"
    assert command["symbol"] == "005930"
    assert command["side"] == "buy"
    assert command["budget"]["amount"] == 30000
    assert command["budget"]["currency"] == "KRW"
    assert command["schedule"]["type"] == "once"
    assert command["requires_auth"] is True
    assert command["requires_risk_approval"] is True
    assert command["risk_level"] == "live_order_possible"
    assert command["execution_policy"]["requires_confirm_live"] is True
    assert command["execution_policy"]["execution_blocked_in_pr56"] is True
    _assert_no_execution_flags(response)


def test_kill_switch_on_is_safety_increasing_without_auth(db_session):
    response = _service().parse(db_session, message="kill switch 켜", context=_context())

    command = response["command"]
    assert command["command_type"] == "SET_KILL_SWITCH"
    assert command["settings_change"]["key"] == "kill_switch"
    assert command["settings_change"]["value"] is True
    assert command["requires_auth"] is False
    assert command["risk_level"] == "settings_safe"
    _assert_no_execution_flags(response)


def test_kill_switch_off_requires_auth_and_does_not_change_setting(db_session):
    response = _service().parse(db_session, message="kill switch 꺼", context=_context())

    command = response["command"]
    assert command["command_type"] == "SET_KILL_SWITCH"
    assert command["settings_change"]["value"] is False
    assert command["requires_auth"] is True
    assert command["risk_level"] == "settings_dangerous"
    _assert_no_execution_flags(response)


def test_dry_run_off_requires_auth(db_session):
    response = _service().parse(db_session, message="dry run 꺼", context=_context())

    command = response["command"]
    assert command["command_type"] == "SET_DRY_RUN"
    assert command["settings_change"]["key"] == "dry_run"
    assert command["settings_change"]["value"] is False
    assert command["requires_auth"] is True
    _assert_no_execution_flags(response)


def test_positions_and_recent_orders_are_read_only(db_session):
    service = _service()

    positions = service.parse(db_session, message="보유종목 보여줘", context=_context())["command"]
    orders = service.parse(db_session, message="오늘 주문 기록 보여줘", context=_context())["command"]

    assert positions["command_type"] == "SHOW_POSITIONS"
    assert positions["risk_level"] == "read_only"
    assert positions["requires_auth"] is False
    assert orders["command_type"] == "SHOW_RECENT_ORDERS"
    assert orders["risk_level"] == "read_only"
    assert orders["requires_auth"] is False


def test_auto_buy_enable_requires_auth_and_warns_no_setting_change(db_session):
    response = _service().parse(db_session, message="auto buy 켜", context=_context())

    command = response["command"]
    assert command["command_type"] == "SET_KIS_LIVE_AUTO_BUY"
    assert command["settings_change"]["value"] is True
    assert command["requires_auth"] is True
    assert command["requires_risk_approval"] is True
    assert command["high_risk"] is True
    assert "비활성 상태로 유지" in command["user_visible_summary"]
    _assert_no_execution_flags(response)


def test_ambiguous_buy_request_needs_clarification(db_session):
    response = _service().parse(db_session, message="삼성전자 사줘", context=_context())

    command = response["command"]
    assert command["needs_clarification"] is True
    assert command["clarification_question"]
    assert command["symbol"] == "005930"
    assert command["side"] == "buy"
    _assert_no_execution_flags(response)


class _FakeMalformedResponses:
    def create(self, **kwargs):
        return SimpleNamespace(output_text="this is not json")


class _FakeMalformedClient:
    responses = _FakeMalformedResponses()


def test_malformed_gpt_response_uses_safe_fallback(db_session):
    response = _service(openai_client=_FakeMalformedClient()).parse(
        db_session,
        message="오늘 삼성전자 살만한지 봐줘",
        context=_context(),
    )

    assert response["parser_status"] == "failed_fallback_used"
    assert response["error_message"]
    assert response["command"]["command_type"] == "RUN_SINGLE_SYMBOL_ANALYSIS"
    _assert_no_execution_flags(response)
