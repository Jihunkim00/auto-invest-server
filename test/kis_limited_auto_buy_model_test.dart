import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_limited_auto_buy.dart';

void main() {
  test('parses disabled limited auto buy response', () {
    final result = KisLimitedAutoBuy.fromJson({
      'status': 'ok',
      'mode': 'limited_auto_buy',
      'result': 'blocked',
      'action': 'hold',
      'reason': 'limited_auto_buy_disabled',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'scheduler_real_order_enabled': false,
      'checks': {'kis_limited_auto_buy_enabled': false},
      'safety': {'max_orders_per_day': 1, 'max_notional_pct': 0.03},
    });

    expect(result.mode, 'limited_auto_buy');
    expect(result.result, 'blocked');
    expect(result.reason, 'limited_auto_buy_disabled');
    expect(result.realOrderSubmitted, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
    expect(result.manualSubmitCalled, isFalse);
    expect(result.check('kis_limited_auto_buy_enabled'), isFalse);
    expect(result.safetyInt('max_orders_per_day'), 1);
  });

  test('parses submitted limited auto buy response', () {
    final result = KisLimitedAutoBuy.fromJson({
      'status': 'ok',
      'mode': 'limited_auto_buy',
      'result': 'submitted',
      'action': 'buy',
      'reason': 'Limited auto buy submitted after all safety gates passed.',
      'symbol': '005930',
      'quantity': 3,
      'notional': 216000,
      'final_score': 82.5,
      'confidence': 0.76,
      'order_id': 123,
      'broker_order_id': 'BUY123',
      'kis_odno': 'BUY123',
      'real_order_submitted': true,
      'broker_submit_called': true,
      'manual_submit_called': false,
      'auto_buy_enabled': true,
      'scheduler_real_order_enabled': false,
      'checks': {'score_threshold_ok': true},
      'safety': {'max_positions': 3},
      'audit_metadata': {'source': 'kis_limited_auto_buy'},
    });

    expect(result.submitted, isTrue);
    expect(result.action, 'buy');
    expect(result.symbol, '005930');
    expect(result.quantity, 3);
    expect(result.notional, 216000);
    expect(result.finalScore, 82.5);
    expect(result.confidence, 0.76);
    expect(result.kisOdno, 'BUY123');
    expect(result.manualSubmitCalled, isFalse);
    expect(result.auditMetadata['source'], 'kis_limited_auto_buy');
  });
}
