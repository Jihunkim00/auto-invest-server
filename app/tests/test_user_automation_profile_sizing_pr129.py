import pytest
from app.services.user_trading_execution_service import UserTradingExecutionService


def _snapshot(*, portfolio_value: float, buying_power: float) -> dict:
    return {
        'account': {
            'portfolio_value': portfolio_value,
            'equity': portfolio_value,
            'buying_power': buying_power,
            'cash': buying_power,
        },
        'positions': [],
        'open_orders': [],
    }


def _profile_context(**values: object) -> dict:
    context = {
        'profile_id': 8,
        'sizing_source': 'automation_profile',
        'sizing_mode': 'fixed_budget',
        'effective_entry_budget_krw': 48000.0,
        'profile_budget_krw': 48000.0,
        'fixed_budget_krw': 50000.0,
        'target_position_pct': 10.0,
        'max_position_pct': 12.0,
        'max_total_exposure_pct': 30.0,
        'max_open_positions': 1,
        'max_order_notional_krw': 48000.0,
        'symbol': '010170',
    }
    context.update(values)
    return context


def test_fixed_budget_uses_profile_budget_and_integer_flooring():
    sizing = UserTradingExecutionService._size_profile_order(
        snapshot=_snapshot(portfolio_value=50000.0, buying_power=50000.0),
        price=18370.0,
        profile_context=_profile_context(),
    )

    assert sizing['sizing_source'] == 'automation_profile'
    assert sizing['sizing_mode'] == 'fixed_budget'
    assert sizing['profile_budget_krw'] == 48000.0
    assert sizing['target_notional'] == 48000.0
    assert sizing['quantity'] == 2
    assert sizing['notional'] == 36740.0


def test_fixed_budget_respects_buying_power_and_order_cap():
    cash_limited = UserTradingExecutionService._size_profile_order(
        snapshot=_snapshot(portfolio_value=200000.0, buying_power=35000.0),
        price=10000.0,
        profile_context=_profile_context(
            effective_entry_budget_krw=100000.0,
            profile_budget_krw=100000.0,
            fixed_budget_krw=100000.0,
            max_order_notional_krw=100000.0,
        ),
    )
    order_capped = UserTradingExecutionService._size_profile_order(
        snapshot=_snapshot(portfolio_value=200000.0, buying_power=200000.0),
        price=15000.0,
        profile_context=_profile_context(
            effective_entry_budget_krw=100000.0,
            profile_budget_krw=100000.0,
            fixed_budget_krw=100000.0,
            max_order_notional_krw=48000.0,
        ),
    )

    assert (cash_limited['quantity'], cash_limited['notional']) == (3, 30000.0)
    assert (order_capped['quantity'], order_capped['notional']) == (3, 45000.0)


def test_fixed_budget_blocks_when_one_share_exceeds_budget():
    sizing = UserTradingExecutionService._size_profile_order(
        snapshot=_snapshot(portfolio_value=50000.0, buying_power=50000.0),
        price=18000.0,
        profile_context=_profile_context(
            effective_entry_budget_krw=15000.0,
            profile_budget_krw=15000.0,
        ),
    )

    assert sizing['reason'] == 'quantity_invalid'
    assert sizing['target_notional'] == 15000.0


def test_equity_percentage_mode_uses_profile_target_not_legacy_user_cap():
    sizing = UserTradingExecutionService._size_profile_order(
        snapshot=_snapshot(portfolio_value=1_000_000.0, buying_power=1_000_000.0),
        price=18000.0,
        profile_context=_profile_context(
            sizing_mode='equity_pct',
            effective_entry_budget_krw=None,
            profile_budget_krw=None,
            target_position_pct=10.0,
            max_position_pct=12.0,
            max_total_exposure_pct=30.0,
            max_order_notional_krw=150000.0,
        ),
    )

    assert sizing['sizing_source'] == 'automation_profile'
    assert sizing['target_notional'] == 100000.0
    assert sizing['quantity'] == 5
    assert sizing['notional'] == 90000.0


def test_asset_ratio_is_per_position_and_allows_second_symbol_target():
    sizing = UserTradingExecutionService._size_profile_order(
        snapshot=_snapshot(portfolio_value=1_000_000.0, buying_power=1_000_000.0),
        price=100_000.0,
        profile_context=_profile_context(
            sizing_mode='equity_pct',
            effective_entry_budget_krw=None,
            profile_budget_krw=None,
            target_position_pct=10.0,
            max_position_pct=12.0,
            max_total_exposure_pct=30.0,
            max_open_positions=2,
            max_order_notional_krw=1_000_000.0,
        ),
    )

    assert sizing['target_notional'] == 100000.0
    assert sizing['derived_total_exposure_pct'] == 20.0
    assert sizing['effective_total_exposure_pct'] == 20.0
    assert sizing['quantity'] == 1


def test_asset_ratio_does_not_subtract_other_symbol_exposure_from_new_position():
    snapshot = _snapshot(portfolio_value=1_000_000.0, buying_power=340_000.0)
    snapshot['positions'] = [
        {'symbol': '000001', 'market_value': 330_000.0},
        {'symbol': '000002', 'market_value': 330_000.0},
    ]
    sizing = UserTradingExecutionService._size_profile_order(
        snapshot=snapshot,
        price=330_000.0,
        profile_context=_profile_context(
            sizing_mode='equity_pct',
            effective_entry_budget_krw=None,
            profile_budget_krw=None,
            target_position_pct=33.0,
            max_position_pct=33.0,
            max_total_exposure_pct=30.0,
            max_open_positions=3,
            max_order_notional_krw=1_000_000.0,
        ),
    )

    assert sizing['target_notional'] == 330000.0
    assert sizing['derived_total_exposure_pct'] == 99.0
    assert sizing['effective_total_exposure_pct'] == 99.0
    assert sizing['quantity'] == 1
    assert sizing['notional'] == 330000.0


def test_manual_legacy_sizing_keeps_user_trading_settings_source():
    sizing = UserTradingExecutionService._size_order(
        snapshot=_snapshot(portfolio_value=50000.0, buying_power=50000.0),
        price=100.0,
        max_position_pct=10.0,
    )

    assert sizing['sizing_source'] == 'user_trading_settings'
    assert sizing['sizing_mode'] == 'legacy_percentage'
    assert sizing['quantity'] == 50
    assert sizing['notional'] == 5000.0

def _preflight_service(possible):
    service = UserTradingExecutionService.__new__(UserTradingExecutionService)
    service.kis_live_client_factory = lambda _db, _user, _credentials: type(
        'FakePossibleOrderClient',
        (),
        {'get_possible_buy_order': lambda self, **kwargs: possible},
    )()
    return service


def test_kis_possible_order_blocks_test01_market_buy_without_submit():
    sizing = {'quantity': 1, 'price': 46475.0, 'target_notional': 48000.0}
    result = _preflight_service({
        'symbol': '067310',
        'order_type': 'market',
        'nrcvb_buy_amt': 49751,
        'nrcvb_buy_qty': 0,
        'psbl_qty_calc_unpr': 59300,
        'raw_status': 'ok',
    })._preflight_kis_automatic_buy(None, user=None, credentials={}, symbol='067310', sizing=sizing)
    assert result['reason'] == 'kis_market_buy_qty_unavailable'
    assert sizing['internal_quantity'] == 1
    assert sizing['kis_profile_quantity'] == 0
    assert sizing['final_quantity'] == 0


def test_kis_possible_order_allows_one_share():
    sizing = {'quantity': 1, 'price': 46475.0, 'target_notional': 48000.0}
    result = _preflight_service({
        'nrcvb_buy_amt': 49751,
        'nrcvb_buy_qty': 1,
        'psbl_qty_calc_unpr': 46475,
        'raw_status': 'ok',
    })._preflight_kis_automatic_buy(None, user=None, credentials={}, symbol='067310', sizing=sizing)
    assert result['reason'] is None
    assert sizing['final_quantity'] == 1


def test_kis_possible_order_never_expands_internal_risk_quantity():
    sizing = {'quantity': 1, 'price': 10000.0, 'target_notional': 10000.0}
    result = _preflight_service({
        'nrcvb_buy_amt': 100000,
        'nrcvb_buy_qty': 5,
        'psbl_qty_calc_unpr': 10000,
        'raw_status': 'ok',
    })._preflight_kis_automatic_buy(None, user=None, credentials={}, symbol='067310', sizing=sizing)
    assert result['reason'] is None
    assert sizing['final_quantity'] == 1


def test_kis_possible_order_failure_is_fail_safe():
    service = UserTradingExecutionService.__new__(UserTradingExecutionService)
    service.kis_live_client_factory = lambda _db, _user, _credentials: type(
        'UnavailableClient',
        (),
        {'get_possible_buy_order': lambda self, **kwargs: (_ for _ in ()).throw(RuntimeError('secret-value'))},
    )()
    sizing = {'quantity': 1, 'price': 10000.0, 'target_notional': 10000.0}
    result = service._preflight_kis_automatic_buy(None, user=None, credentials={}, symbol='067310', sizing=sizing)
    assert result['reason'] == 'kis_possible_order_unavailable'
    assert sizing['final_quantity'] == 0
    assert sizing['kis_possible_order']['error_type'] == 'RuntimeError'
    assert 'secret-value' not in str(sizing)


def test_kis_rejection_diagnostics_are_safe_and_preserved():
    from app.services.user_broker_account_service import (
        UserBrokerUnavailableError,
        _require_kis_order_response,
    )

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {'rt_cd': '1', 'msg_cd': 'SOME_CODE', 'msg1': 'safe rejection message'}

    with pytest.raises(UserBrokerUnavailableError) as raised:
        _require_kis_order_response(Response())
    assert raised.value.details == {
        'error_type': 'kis_order_rejected',
        'http_status': 200,
        'rt_cd': '1',
        'msg_cd': 'SOME_CODE',
        'msg1': 'safe rejection message',
    }

    diagnostics = UserTradingExecutionService._safe_broker_diagnostics(
        UserBrokerUnavailableError(
            'rejected',
            details={
                'error_type': 'kis_order_rejected',
                'http_status': 200,
                'rt_cd': '1',
                'msg_cd': 'SOME_CODE',
                'msg1': 'safe rejection message',
                'app_key': 'secret',
                'access_token': 'token',
                'account_no': '12345678',
            },
        )
    )
    assert 'app_key' not in diagnostics
    assert 'access_token' not in diagnostics
    assert 'account_no' not in diagnostics
