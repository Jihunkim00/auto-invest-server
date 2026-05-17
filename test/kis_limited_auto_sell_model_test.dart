import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_limited_auto_sell.dart';

void main() {
  test('parses disabled blocked response safely', () {
    final result = KisLimitedAutoSell.fromJson({
      'status': 'ok',
      'mode': 'limited_auto_sell',
      'result': 'blocked',
      'action': 'hold',
      'reason': 'limited_auto_sell_disabled',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
      'checks': {'kis_limited_auto_sell_enabled': false, 'dry_run': true},
      'safety': {'max_orders_per_day': 1, 'max_notional_pct': 0.03},
    });

    expect(result.mode, 'limited_auto_sell');
    expect(result.result, 'blocked');
    expect(result.submitted, isFalse);
    expect(result.realOrderSubmitted, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
    expect(result.manualSubmitCalled, isFalse);
    expect(result.autoBuyEnabled, isFalse);
    expect(result.schedulerRealOrderEnabled, isFalse);
    expect(result.check('kis_limited_auto_sell_enabled'), isFalse);
    expect(result.safetyInt('max_orders_per_day'), 1);
    expect(result.safetyDouble('max_notional_pct'), 0.03);
  });

  test('parses submitted response and audit metadata', () {
    final result = KisLimitedAutoSell.fromJson({
      'status': 'ok',
      'mode': 'limited_auto_sell',
      'result': 'submitted',
      'action': 'sell',
      'reason': 'Limited auto sell submitted.',
      'symbol': '005930',
      'quantity': 1,
      'trigger': 'stop_loss',
      'trigger_source': 'cost_basis_pl_pct',
      'order_id': 123,
      'broker_order_id': 'AUTO123',
      'kis_odno': 'AUTO123',
      'real_order_submitted': true,
      'broker_submit_called': true,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': true,
      'scheduler_real_order_enabled': false,
      'unrealized_pl': -4000,
      'unrealized_pl_pct': -0.04,
      'checks': {'queue_item_reviewed': true},
      'safety': {'stop_loss_only': true},
      'audit_metadata': {'source': 'kis_limited_auto_sell'},
    });

    expect(result.submitted, isTrue);
    expect(result.symbol, '005930');
    expect(result.quantity, 1);
    expect(result.trigger, 'stop_loss');
    expect(result.orderId, 123);
    expect(result.kisOdno, 'AUTO123');
    expect(result.manualSubmitCalled, isFalse);
    expect(result.auditMetadata['source'], 'kis_limited_auto_sell');
  });
}
