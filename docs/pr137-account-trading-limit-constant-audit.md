# PR137 remaining constant audit

Every matching line is classified below. Tests retain fixture amounts and account-policy assertions.

- Operation Test4 explicit order/price cap (separate domain): 39 matches
- explicit regular-account 1M position default: 2 matches
- independent Agent Chat settings validation upper bound (10M): 1 matches
- isolated test fixture or policy assertion: 136 matches
- market-data unit multiplier: 1 matches
- nullable compatibility telemetry; no enforcement: 8 matches
- preserved score/session/positions/TP/cash safety; money ceiling removed: 11 matches

| Classification | Location | Match |
| --- | --- | --- |
| explicit regular-account 1M position default | `app/db/init_db.py:33` | `'account_max_position_notional_krw': 1_000_000.0,` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/init_db.py:504` | `operation_test4_max_order_notional_krw FLOAT NOT NULL DEFAULT 1000000.0,` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/init_db.py:505` | `operation_test4_price_cap_krw FLOAT NOT NULL DEFAULT 1000000.0,` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/init_db.py:1234` | `price_cap_krw FLOAT NOT NULL DEFAULT 1000000.0,` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/init_db.py:1235` | `max_order_notional_krw FLOAT NOT NULL DEFAULT 1000000.0,` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/init_db.py:1271` | `"price_cap_krw": "FLOAT DEFAULT 1000000.0",` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/init_db.py:1272` | `"max_order_notional_krw": "FLOAT DEFAULT 1000000.0",` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/init_db.py:2584` | `"operation_test4_max_order_notional_krw": "FLOAT DEFAULT 1000000.0",` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/init_db.py:2585` | `"operation_test4_price_cap_krw": "FLOAT DEFAULT 1000000.0",` |
| explicit regular-account 1M position default | `app/db/models.py:37` | `default=lambda ctx: _account_limit_default(ctx, 1_000_000.0),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/models.py:705` | `operation_test4_max_order_notional_krw = Column(Float, nullable=False, default=1_000_000.0)` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/models.py:706` | `operation_test4_price_cap_krw = Column(Float, nullable=False, default=1_000_000.0)` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/models.py:1125` | `price_cap_krw = Column(Float, nullable=False, default=1_000_000.0)` |
| Operation Test4 explicit order/price cap (separate domain) | `app/db/models.py:1126` | `max_order_notional_krw = Column(Float, nullable=False, default=1_000_000.0)` |
| Operation Test4 explicit order/price cap (separate domain) | `app/schemas/operation_test.py:140` | `price_cap_krw: float = Field(default=1_000_000.0, gt=0)` |
| nullable compatibility telemetry; no enforcement | `app/schemas/strategy_dry_run_auto_buy.py:154` | `hard_max_order_notional_krw: float \| None = None` |
| nullable compatibility telemetry; no enforcement | `app/schemas/strategy_risk.py:47` | `hard_max_order_notional_krw: float \| None = None` |
| nullable compatibility telemetry; no enforcement | `app/schemas/strategy_risk.py:86` | `hard_max_order_notional_krw: float \| None = None` |
| nullable compatibility telemetry; no enforcement | `app/services/automation_profile_buy_scheduler_service.py:632` | `'hard_max_order_notional_krw': target.get('hard_max_order_notional_krw'),` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_safety.py:7` | `TEST4_HARD_SAFETY = {` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_safety.py:33` | `TEST4_HARD_SAFETY['min_final_score'],` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_safety.py:37` | `str(entry.get('no_new_entry_after') or TEST4_HARD_SAFETY['no_new_entry_after']),` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_safety.py:38` | `TEST4_HARD_SAFETY['no_new_entry_after'],` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_safety.py:41` | `TEST4_HARD_SAFETY['max_open_positions'],` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_safety.py:42` | `int(effective.get('max_open_positions') or TEST4_HARD_SAFETY['max_open_positions']),` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_safety.py:49` | `TEST4_HARD_SAFETY['take_profit_max_pct'],` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_safety.py:50` | `max(TEST4_HARD_SAFETY['take_profit_min_pct'], requested_take_profit),` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_service.py:20` | `from app.services.automation_profile_safety import TEST4_HARD_SAFETY, effective_profile_settings` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_service.py:678` | `'safety_hard_floors': TEST4_HARD_SAFETY,` |
| preserved score/session/positions/TP/cash safety; money ceiling removed | `app/services/automation_profile_service.py:811` | `'safety_hard_floors': TEST4_HARD_SAFETY,` |
| market-data unit multiplier | `app/services/kr_market_context_service.py:28` | `INVESTOR_FLOW_RAW_MULTIPLIER = 1_000_000` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:1307` | `"operation_test4_max_order_notional_krw": 1_000_000.0,` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:1308` | `"operation_test4_price_cap_krw": 1_000_000.0,` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:1825` | `max_order_notional_krw=float(runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0)),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:1826` | `price_cap_krw=float(runtime.get("operation_test4_price_cap_krw", 1_000_000.0)),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:1843` | `"price_cap_krw": runtime.get("operation_test4_price_cap_krw", 1_000_000.0),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:1844` | `"max_order_notional_krw": runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:3272` | `max_order_notional_krw=float(runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0)),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:3273` | `price_cap_krw=float(runtime.get("operation_test4_price_cap_krw", 1_000_000.0)),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:3322` | `"price_cap_krw": runtime.get("operation_test4_price_cap_krw", 1_000_000.0),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:3323` | `"max_order_notional_krw": runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:3607` | `price_cap_krw=float(sizing.get("price_cap_krw") or 1_000_000.0),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:3609` | `sizing.get("max_order_notional_krw") or 1_000_000.0` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:3809` | `runtime.get("operation_test4_max_order_notional_krw", 1_000_000.0)` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:3829` | `"price_cap_krw": runtime.get("operation_test4_price_cap_krw", 1_000_000.0),` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_service.py:3831` | `"operation_test4_max_order_notional_krw", 1_000_000.0` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_sizing.py:10` | `DEFAULT_MAX_ORDER_NOTIONAL_KRW = 1_000_000.0` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_sizing.py:11` | `DEFAULT_PRICE_CAP_KRW = 1_000_000.0` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/operation_test4_watchlist.py:19` | `DEFAULT_PRICE_CAP_KRW = 1_000_000.0` |
| nullable compatibility telemetry; no enforcement | `app/services/profile_aware_dry_run_auto_buy_service.py:1174` | `"hard_max_order_notional_krw": None,` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/runtime_setting_service.py:258` | `"operation_test4_max_order_notional_krw": 1_000_000.0,` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/runtime_setting_service.py:259` | `"operation_test4_price_cap_krw": 1_000_000.0,` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/runtime_setting_service.py:797` | `getattr(row, "operation_test4_max_order_notional_krw", 1_000_000.0)` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/runtime_setting_service.py:798` | `or 1_000_000.0` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/runtime_setting_service.py:801` | `getattr(row, "operation_test4_price_cap_krw", 1_000_000.0)` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/runtime_setting_service.py:802` | `or 1_000_000.0` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/runtime_setting_service.py:1136` | `or 1_000_000.0` |
| Operation Test4 explicit order/price cap (separate domain) | `app/services/runtime_setting_service.py:1141` | `float(settings.get("operation_test4_price_cap_krw") or 1_000_000.0),` |
| independent Agent Chat settings validation upper bound (10M) | `app/services/runtime_setting_service.py:2232` | `maximum=10000000.0,` |
| nullable compatibility telemetry; no enforcement | `app/services/strategy_profile_sizing_service.py:94` | `'hard_max_order_notional_krw': None,` |
| nullable compatibility telemetry; no enforcement | `app/services/strategy_risk_budget_service.py:409` | `"hard_max_order_notional_krw": hard_max_krw,` |
| nullable compatibility telemetry; no enforcement | `app/services/target_aware_risk_service.py:201` | `"hard_max_order_notional_krw": snapshot["hard_max_order_notional_krw"],` |
| isolated test fixture or policy assertion | `app/tests/integration/test_pr129_profile_shadow_replay.py:46` | `return {"cash": 1_000_000.0, "orderable_cash": 1_000_000.0, "total_asset_value": 1_000_000.0}` |
| isolated test fixture or policy assertion | `app/tests/integration/test_pr129_profile_shadow_replay.py:189` | `"account": {"currency": "KRW", "portfolio_value": 1_000_000.0,` |
| isolated test fixture or policy assertion | `app/tests/integration/test_pr129_profile_shadow_replay.py:190` | `"equity": 1_000_000.0, "buying_power": 1_000_000.0, "cash": 1_000_000.0},` |
| isolated test fixture or policy assertion | `app/tests/integration/test_pr129_profile_shadow_replay.py:197` | `capital={"initial_budget_krw": 1_000_000.0, "fixed_budget": 1_000_000.0,` |
| isolated test fixture or policy assertion | `app/tests/integration/test_pr129_tomorrow_preflight.py:262` | `fixed_budget=1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/integration/test_pr129_tomorrow_preflight.py:315` | `'portfolio_value': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/integration/test_pr129_tomorrow_preflight.py:316` | `'equity': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/integration/test_pr129_tomorrow_preflight.py:317` | `'buying_power': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/integration/test_pr129_tomorrow_preflight.py:318` | `'cash': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:44` | `@pytest.mark.parametrize('role,total,position', [('admin', None, None), ('user', 10_000_000, 1_000_000)])` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:56` | `('user', 1_000_000, 5_000_000, 9_600_000, 0, 1, 400_000, 'account_total_exposure_cap'),` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:124` | `assert _calculate(db_session, second)['effective_order_cap_krw'] == 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:159` | `assert rows[1]['account_max_position_notional_krw'] == 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:256` | `admin = _user(db_session, 'admin', account_max_total_exposure_krw=1_000_000)` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:270` | `assert admin.account_max_total_exposure_krw == 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:313` | `assert client.get(f'/admin/users/{second.id}').json()['trading_limits']['max_position_notional_krw'] == 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:319` | `assert audit.previous_max_position_notional_krw == 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:431` | `admin = _user(db_session, 'admin', account_max_total_exposure_krw=1_000_000)` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:440` | `assert lag['pending_buy_exposure_krw'] == 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:442` | `reflected = _calculate(db_session, admin, positions=_positions(1_000_000, 1_000_000))` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:444` | `assert reflected['current_account_exposure_krw'] == 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:453` | `order.notional = 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_account_trading_limits_pr137.py:472` | `'account_max_total_exposure_krw': None, 'account_max_position_notional_krw': 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_audit.py:103` | `"agent_chat_live_order_max_notional_krw": 1000000,` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_emergency_controls.py:32` | `assert controls["max_notional_limit"] == 1000000` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_emergency_controls.py:104` | `"agent_chat_live_order_max_notional_krw": 1000000,` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_idempotency.py:164` | `"agent_chat_live_order_max_notional_krw": 1000000,` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_routes.py:168` | `"agent_chat_live_order_max_notional_krw": 1000000,` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_safety.py:110` | `"agent_chat_live_order_max_notional_krw": 1000000,` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_service.py:278` | `"agent_chat_live_order_max_notional_krw": 1000000,` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_service.py:341` | `return {'cash': 1_000_000, 'orderable_cash': 1_000_000, 'total_asset_value': 1_000_000}` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_service.py:371` | `available_cash=1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_status_routes.py:124` | `"agent_chat_live_order_max_notional_krw": 1000000,` |
| isolated test fixture or policy assertion | `app/tests/test_agent_chat_live_order_sync.py:162` | `"agent_chat_live_order_max_notional_krw": 1000000,` |
| isolated test fixture or policy assertion | `app/tests/test_automation_profiles.py:102` | `'equity': 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_automation_shadow_cli.py:35` | `"initial_budget_krw": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_automation_shadow_cli.py:36` | `"fixed_budget": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_event_risk_kis_preview.py:115` | `"volume": 1000000 + (index * 10000),` |
| isolated test fixture or policy assertion | `app/tests/test_guarded_live_sell.py:27` | `"kis_max_manual_order_amount_krw": 1_000_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_account_state_cache_service.py:79` | `return {"output2": [{"dnca_tot_amt": "1000000", "tot_evlu_amt": "2000000"}], "output1": [{"pdno": "005930", "hldg_qty": "1", "prpr": "96000", "pchs_avg_pric": "100000"}]}` |
| isolated test fixture or policy assertion | `app/tests/test_kis_account_state_cache_service.py:115` | `return {"output2": [{"dnca_tot_amt": "1000000", "tot_evlu_amt": "2000000"}], "output1": [{"pdno": "005930", "hldg_qty": "1", "prpr": "96000", "pchs_avg_pric": "100000"}]}` |
| isolated test fixture or policy assertion | `app/tests/test_kis_account_state_cache_service.py:204` | `"output2": [{"dnca_tot_amt": "1000000", "tot_evlu_amt": "1000000"}],` |
| isolated test fixture or policy assertion | `app/tests/test_kis_account_state_cache_service.py:231` | `"output2": [{"dnca_tot_amt": "1000000", "tot_evlu_amt": "1000000"}],` |
| isolated test fixture or policy assertion | `app/tests/test_kis_automation_execution_core.py:29` | `return {'cash': 1_000_000, 'orderable_cash': 1_000_000, 'total_asset_value': 1_000_000}` |
| isolated test fixture or policy assertion | `app/tests/test_kis_automation_execution_core.py:41` | `"orderable_cash": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_automation_execution_core.py:61` | `capital={'sizing_mode': 'fixed_budget', 'fixed_budget': 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_automation_execution_core.py:62` | `'max_order_notional_krw': 1_000_000},` |
| isolated test fixture or policy assertion | `app/tests/test_kis_automation_execution_core.py:121` | `max_order_notional_krw=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_buy_shadow_decision.py:382` | `preview=_preview(candidates=[_candidate(current_price=1_000_000)])` |
| isolated test fixture or policy assertion | `app/tests/test_kis_buy_shadow_decision.py:459` | `fake_client=_FakeClient(balance={"cash": 1_000_000})` |
| isolated test fixture or policy assertion | `app/tests/test_kis_limited_auto_buy_execution_review.py:364` | `"total_asset_value": 10000000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_limited_auto_buy_execution_review.py:539` | `"total_asset_value": 10000000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_limited_auto_sell.py:60` | `"cash": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_limited_auto_sell.py:205` | `"balance": {"cash": 1_000_000, "total_asset_value": 10_000_000},` |
| isolated test fixture or policy assertion | `app/tests/test_kis_limited_auto_sell.py:972` | `"balance": {"cash": 1000000},` |
| isolated test fixture or policy assertion | `app/tests/test_kis_manual_exit_audit.py:30` | `"kis_max_manual_order_amount_krw": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_manual_exit_audit.py:107` | `lambda self: {"currency": "KRW", "cash": 1_000_000.0},` |
| isolated test fixture or policy assertion | `app/tests/test_kis_manual_order_submit.py:123` | `lambda self: {"currency": "KRW", "cash": 1000000.0},` |
| isolated test fixture or policy assertion | `app/tests/test_kis_manual_order_submit.py:353` | `lambda: _settings(kis_max_manual_order_amount_krw=1000000),` |
| isolated test fixture or policy assertion | `app/tests/test_kis_manual_order_submit.py:369` | `kis_max_manual_order_qty=0, kis_max_manual_order_amount_krw=1000000` |
| isolated test fixture or policy assertion | `app/tests/test_kis_order_audit.py:33` | `"kis_max_manual_order_amount_krw": 1000000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_order_audit.py:190` | `"available_cash": 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_order_audit.py:275` | `assert recent["audit_metadata"]["available_cash"] == 1000000.0` |
| isolated test fixture or policy assertion | `app/tests/test_kis_order_validation.py:54` | `lambda self: {"currency": "KRW", "cash": 1_000_000.0},` |
| isolated test fixture or policy assertion | `app/tests/test_kis_order_validation.py:116` | `assert body["available_cash"] == 1000000.0` |
| isolated test fixture or policy assertion | `app/tests/test_kis_order_validation.py:167` | `assert body["available_cash"] == 1000000.0` |
| isolated test fixture or policy assertion | `app/tests/test_kis_read_only_endpoints.py:525` | `assert body["cash"] == 1000000.0` |
| isolated test fixture or policy assertion | `app/tests/test_kis_scheduler_live_integration.py:393` | `self._cached = {"source": "fresh", "fetch_success": True, "positions": [], "balance": {"cash": 1000000}}` |
| isolated test fixture or policy assertion | `app/tests/test_kis_scheduler_simulation.py:326` | `lambda self: {"cash": 1000000, "total_asset_value": 2000000, "unrealized_pl": 0},` |
| isolated test fixture or policy assertion | `app/tests/test_kis_scheduler_simulation.py:383` | `lambda self: {"cash": 1000000, "total_asset_value": 2000000, "unrealized_pl": 0},` |
| isolated test fixture or policy assertion | `app/tests/test_kis_scheduler_simulation.py:437` | `lambda self: {"cash": 1000000, "total_asset_value": 2000000, "unrealized_pl": 0},` |
| isolated test fixture or policy assertion | `app/tests/test_kis_scheduler_simulation.py:490` | `lambda self: {"cash": 1000000, "total_asset_value": 2000000, "unrealized_pl": 0},` |
| isolated test fixture or policy assertion | `app/tests/test_kis_single_symbol_analysis_service.py:75` | `"volume": 1000000 + index * 1000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_single_symbol_trading.py:32` | `"kis_max_manual_order_amount_krw": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_kis_watchlist_preview.py:49` | `"volume": 1000000 + (index * 10000),` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_entry.py:51` | `"total_asset_value": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_entry.py:52` | `"orderable_cash": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_entry.py:76` | `available_cash = 1_000_000.0` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_entry.py:181` | `"price_cap_krw: 1000000\n"` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_entry.py:222` | `"equity": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_entry.py:223` | `"orderable_cash": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_entry.py:246` | `"orderable_cash": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_entry.py:408` | `"current_price": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_next_session.py:166` | `"orderable_cash": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_readiness.py:226` | `"price_cap_krw: 1000000",` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_readiness.py:320` | `"equity": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_readiness.py:321` | `"orderable_cash": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_scheduler.py:415` | `"orderable_cash": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_scheduler.py:514` | `"equity": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_scheduler.py:515` | `"orderable_cash": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:16` | `equity=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:17` | `orderable_cash=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:24` | `assert result.estimated_notional <= 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:30` | `equity=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:31` | `orderable_cash=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:32` | `current_price=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:35` | `equity=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:36` | `orderable_cash=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:46` | `equity=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:59` | `equity=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:70` | `equity=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_sizing.py:71` | `orderable_cash=1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_start.py:510` | `"equity": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_watchlist.py:76` | `assert validate_quote({"current_price": 1_000_000}).reasons == (` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_watchlist.py:98` | `quotes["000050"] = {"current_price": 1_000_000}` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_watchlist.py:112` | `f"{index:06d}": {"current_price": 1_000_000 if index <= 6 else 10_000}` |
| isolated test fixture or policy assertion | `app/tests/test_operation_test4_watchlist.py:203` | `f"{index:06d}": {"current_price": 10_000 if index <= 44 else 1_000_000}` |
| isolated test fixture or policy assertion | `app/tests/test_pr110_final_buy_readiness.py:55` | `return {'cash': 1_000_000, 'orderable_cash': 1_000_000}` |
| isolated test fixture or policy assertion | `app/tests/test_pr110_final_buy_readiness.py:75` | `'orderable_cash': 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_pr110_fixed_budget_sizing.py:175` | `assert result["hard_max_order_notional_krw"] is None` |
| isolated test fixture or policy assertion | `app/tests/test_pr110_fixed_budget_sizing.py:304` | `balance={"cash": 42_270, "orderable_cash": 42_270, "total_asset_value": 1_000_000},` |
| isolated test fixture or policy assertion | `app/tests/test_pr110_fixed_budget_sizing.py:418` | `_request(requested_notional_krw=1_000_000),` |
| isolated test fixture or policy assertion | `app/tests/test_strategy_live_auto_buy_service.py:68` | `"total_assets_krw": 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_strategy_live_auto_buy_service.py:93` | `available_cash: float = 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_strategy_live_auto_buy_service.py:189` | `return {'cash': 1_000_000, 'orderable_cash': 1_000_000, 'total_asset_value': 2_000_000}` |
| isolated test fixture or policy assertion | `app/tests/test_strategy_live_auto_buy_service.py:195` | `return {'raw_status': 'ok', 'orderable_cash': 1_000_000,` |
| isolated test fixture or policy assertion | `app/tests/test_strategy_live_auto_buy_service.py:220` | `balance_loader=lambda db: dict(balance or {"cash": 1_000_000}),` |
| isolated test fixture or policy assertion | `app/tests/test_strategy_live_auto_buy_service.py:488` | `assert result["available_cash_krw"] == 1_000_000` |
| isolated test fixture or policy assertion | `app/tests/test_strategy_live_auto_exit_service.py:39` | `available_cash: float = 1000000` |
| isolated test fixture or policy assertion | `app/tests/test_target_aware_risk_service.py:64` | `balance_payload = balance if balance is not None else {"total_asset_value": 1_000_000, "orderable_cash": 1_000_000}` |
| isolated test fixture or policy assertion | `app/tests/test_user_auto_trading_scheduler_pr129.py:165` | `'nrcvb_buy_amt': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_auto_trading_scheduler_pr129.py:921` | `'portfolio_value': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_auto_trading_scheduler_pr129.py:922` | `'equity': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_auto_trading_scheduler_pr129.py:923` | `'buying_power': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_auto_trading_scheduler_pr129.py:924` | `'cash': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_auto_trading_scheduler_pr129.py:1448` | `'portfolio_value': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_auto_trading_scheduler_pr129.py:1449` | `'equity': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_auto_trading_scheduler_pr129.py:1450` | `'buying_power': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_auto_trading_scheduler_pr129.py:1451` | `'cash': 1000000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_automation_profile_sizing_pr129.py:96` | `snapshot=_snapshot(portfolio_value=1_000_000.0, buying_power=1_000_000.0),` |
| isolated test fixture or policy assertion | `app/tests/test_user_automation_profile_sizing_pr129.py:117` | `snapshot=_snapshot(portfolio_value=1_000_000.0, buying_power=1_000_000.0),` |
| isolated test fixture or policy assertion | `app/tests/test_user_automation_profile_sizing_pr129.py:127` | `max_order_notional_krw=1_000_000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_automation_profile_sizing_pr129.py:138` | `snapshot = _snapshot(portfolio_value=1_000_000.0, buying_power=340_000.0)` |
| isolated test fixture or policy assertion | `app/tests/test_user_automation_profile_sizing_pr129.py:154` | `max_order_notional_krw=1_000_000.0,` |
| isolated test fixture or policy assertion | `app/tests/test_user_broker_accounts.py:124` | `'dnca_tot_amt': '1000000',` |
| isolated test fixture or policy assertion | `app/tests/test_user_broker_accounts.py:247` | `assert snapshot_a['account']['cash'] == 1000000.0` |
