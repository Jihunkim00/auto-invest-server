import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_limited_auto_buy.dart';

void main() {
  test('parses default disabled buy readiness status response', () {
    final result = KisLimitedAutoBuy.fromJson({
      'status': 'ok',
      'mode': 'kis_limited_auto_buy_status',
      'result': 'blocked',
      'action': 'hold',
      'reason': 'auto_buy_execution_disabled',
      'primary_block_reason': 'auto_buy_execution_disabled',
      'live_auto_buy_enabled': false,
      'limited_auto_buy_enabled': false,
      'buy_readiness_enabled': true,
      'dry_run': true,
      'kill_switch': false,
      'kis_real_order_enabled': false,
      'market_open': false,
      'entry_allowed_now': false,
      'cash_available': 3000000,
      'daily_buy_count': 0,
      'daily_buy_limit': 1,
      'max_notional_pct': 0.03,
      'real_order_submit_allowed': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'validation_called': false,
      'scheduler_real_orders_enabled': false,
      'block_reasons': ['auto_buy_execution_disabled'],
      'checks': {'kis_limited_auto_buy_enabled': false},
      'safety': {
        'buy_readiness_only': true,
        'auto_buy_execution_enabled': false,
        'max_orders_per_day': 1,
      },
    });

    expect(result.mode, 'kis_limited_auto_buy_status');
    expect(result.liveAutoBuyEnabled, isFalse);
    expect(result.limitedAutoBuyEnabled, isFalse);
    expect(result.buyReadinessEnabled, isTrue);
    expect(result.realOrderSubmitAllowed, isFalse);
    expect(result.validationCalled, isFalse);
    expect(result.blockReasons, contains('auto_buy_execution_disabled'));
    expect(result.check('kis_limited_auto_buy_enabled'), isFalse);
    expect(result.safetyFlag('auto_buy_execution_enabled'), isFalse);
  });

  test('parses buy-ready candidate as readiness only', () {
    final result = KisLimitedAutoBuy.fromJson(_payload());

    expect(result.mode, 'kis_limited_auto_buy_preflight');
    expect(result.result, 'ready');
    expect(result.action, 'buy_ready');
    expect(result.buyReady, isTrue);
    expect(result.realOrderSubmitted, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
    expect(result.manualSubmitCalled, isFalse);
    expect(result.validationCalled, isFalse);
    expect(result.finalCandidate?.symbol, '005930');
    expect(result.finalCandidate?.companyName, 'Samsung Electronics');
    expect(result.finalCandidate?.finalBuyScore, 82.5);
    expect(result.finalCandidate?.requiredBuyScore, 75);
    expect(result.finalCandidate?.buyReadinessOnly, isTrue);
    expect(result.finalCandidate?.buyActionable, isFalse);
    expect(result.rawPayload['source'], 'kis_limited_auto_buy');
  });
}

Map<String, dynamic> _payload() {
  return {
    'status': 'ok',
    'mode': 'kis_limited_auto_buy_preflight',
    'source': 'kis_limited_auto_buy',
    'source_type': 'buy_readiness_only',
    'result': 'ready',
    'action': 'buy_ready',
    'reason': 'buy_readiness_only',
    'primary_block_reason': 'auto_buy_execution_disabled',
    'symbol': '005930',
    'quantity': 4,
    'estimated_notional': 288000,
    'final_buy_score': 82.5,
    'final_sell_score': 12,
    'confidence': 0.76,
    'required_buy_score': 75,
    'buy_sell_spread': 70.5,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'validation_called': false,
    'auto_buy_enabled': false,
    'live_auto_buy_enabled': false,
    'limited_auto_buy_enabled': false,
    'buy_readiness_enabled': true,
    'scheduler_real_orders_enabled': false,
    'block_reasons': ['auto_buy_execution_disabled'],
    'candidates': [_candidate()],
    'final_candidate': _candidate(),
    'checks': {'kis_limited_auto_buy_enabled': false},
    'safety': {'buy_readiness_only': true},
    'audit_metadata': {'source': 'kis_limited_auto_buy'},
  };
}

Map<String, dynamic> _candidate() {
  return {
    'symbol': '005930',
    'company_name': 'Samsung Electronics',
    'status': 'BUY READY',
    'current_price': 72000,
    'available_cash': 3000000,
    'estimated_notional': 288000,
    'suggested_quantity': 4,
    'final_buy_score': 82.5,
    'final_sell_score': 12,
    'confidence': 0.76,
    'required_buy_score': 75,
    'buy_sell_spread': 70.5,
    'entry_ready': true,
    'trade_allowed': false,
    'buy_readiness_only': true,
    'buy_actionable': false,
    'cash_sufficient': true,
    'market_session_allowed': true,
    'block_reasons': [],
    'technical_snapshot': {'EMA20': 70500, 'RSI': 57.5},
  };
}
