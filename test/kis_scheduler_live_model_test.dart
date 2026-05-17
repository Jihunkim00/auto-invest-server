import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_scheduler_live.dart';

void main() {
  test('parses blocked scheduler live response', () {
    final result = KisSchedulerLiveResult.fromJson({
      'status': 'ok',
      'mode': 'kis_scheduler_live_once',
      'result': 'blocked',
      'action': 'hold',
      'reason': 'kis_scheduler_live_disabled',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'scheduler_real_order_enabled': false,
      'checks': {'kis_scheduler_live_enabled': false},
      'safety': {'max_live_orders_per_day': 2},
    });

    expect(result.mode, 'kis_scheduler_live_once');
    expect(result.result, 'blocked');
    expect(result.reason, 'kis_scheduler_live_disabled');
    expect(result.realOrderSubmitted, isFalse);
    expect(result.manualSubmitCalled, isFalse);
    expect(result.check('kis_scheduler_live_enabled'), isFalse);
    expect(result.safetyInt('max_live_orders_per_day'), 2);
  });

  test('parses submitted scheduler live response', () {
    final result = KisSchedulerLiveResult.fromJson({
      'status': 'ok',
      'mode': 'kis_scheduler_live_once',
      'result': 'submitted',
      'action': 'buy',
      'reason': 'Limited auto buy submitted.',
      'order_id': 123,
      'real_order_submitted': true,
      'broker_submit_called': true,
      'manual_submit_called': false,
      'scheduler_real_order_enabled': true,
      'sell_result': {'result': 'blocked'},
      'buy_result': {'result': 'submitted', 'order_id': 123},
    });

    expect(result.submitted, isTrue);
    expect(result.action, 'buy');
    expect(result.orderId, 123);
    expect(result.sellResult['result'], 'blocked');
    expect(result.buyResult['result'], 'submitted');
    expect(result.schedulerRealOrderEnabled, isTrue);
  });
}
