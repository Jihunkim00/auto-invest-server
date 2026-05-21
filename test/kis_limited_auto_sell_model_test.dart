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
      'stop_loss_execution_enabled': false,
      'take_profit_readiness_enabled': true,
      'take_profit_execution_enabled': false,
      'take_profit_non_actionable': true,
      'take_profit_actionable': false,
      'take_profit_readiness_only': false,
      'take_profit_execution_disabled': true,
      'daily_limit_remaining': 1,
      'daily_limit': {'max_orders_per_day': 1, 'submitted_count_today': 0},
      'duplicate_order_check': {'duplicate_open_sell_order': false},
      'validation_status': 'not_called',
      'readiness_labels': ['GUARDED EXECUTION', 'NO BROKER SUBMIT'],
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
    expect(result.stopLossExecutionEnabled, isFalse);
    expect(result.takeProfitReadinessEnabled, isTrue);
    expect(result.takeProfitExecutionEnabled, isFalse);
    expect(result.takeProfitNonActionable, isTrue);
    expect(result.takeProfitActionable, isFalse);
    expect(result.takeProfitExecutionDisabled, isTrue);
    expect(result.dailyLimitRemaining, 1);
    expect(result.dailyLimitInt('max_orders_per_day'), 1);
    expect(result.duplicateOrderFlag('duplicate_open_sell_order'), isFalse);
    expect(result.validationStatus, 'not_called');
    expect(result.readinessLabels, contains('GUARDED EXECUTION'));
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
      'stop_loss_triggered': true,
      'take_profit_triggered': false,
      'stop_loss_execution_enabled': true,
      'take_profit_readiness_enabled': true,
      'take_profit_execution_enabled': false,
      'take_profit_non_actionable': true,
      'take_profit_actionable': false,
      'take_profit_readiness_only': false,
      'take_profit_execution_disabled': false,
      'daily_limit_remaining': 1,
      'daily_limit': {'max_orders_per_day': 1, 'submitted_count_today': 0},
      'duplicate_order_check': {'duplicate_open_sell_order': false},
      'validation_status': 'passed',
      'readiness_labels': ['GUARDED EXECUTION', 'BROKER SUBMIT CALLED'],
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
    expect(result.brokerSubmitActuallyCalled, isTrue);
    expect(result.stopLossTriggered, isTrue);
    expect(result.takeProfitTriggered, isFalse);
    expect(result.stopLossExecutionEnabled, isTrue);
    expect(result.takeProfitExecutionEnabled, isFalse);
    expect(result.validationStatus, 'passed');
    expect(result.auditMetadata['source'], 'kis_limited_auto_sell');
  });

  test('parses take-profit readiness-only response', () {
    final result = KisLimitedAutoSell.fromJson({
      'status': 'ok',
      'mode': 'kis_limited_auto_stop_loss_preflight',
      'source': 'kis_limited_auto_take_profit',
      'source_type': 'take_profit_readiness_only',
      'result': 'preview_only',
      'action': 'review_sell',
      'reason': 'take_profit_readiness_only',
      'take_profit_readiness_enabled': true,
      'take_profit_execution_enabled': false,
      'take_profit_non_actionable': true,
      'take_profit_actionable': false,
      'take_profit_readiness_only': true,
      'take_profit_execution_disabled': true,
      'final_candidate': {
        'symbol': '005930',
        'company_name': 'Samsung Electronics',
        'quantity': 1,
        'unrealized_pl': 3000,
        'unrealized_pl_pct': 0.03,
        'take_profit_triggered': true,
        'take_profit_readiness_only': true,
        'take_profit_actionable': false,
        'take_profit_execution_disabled': true,
        'status': 'TAKE_PROFIT_READY',
      },
      'candidates': const [],
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    });

    expect(result.source, 'kis_limited_auto_take_profit');
    expect(result.sourceType, 'take_profit_readiness_only');
    expect(result.takeProfitTriggered, isTrue);
    expect(result.takeProfitReadinessOnly, isTrue);
    expect(result.takeProfitExecutionDisabled, isTrue);
    expect(result.takeProfitActionable, isFalse);
    expect(result.finalCandidate?.status, 'TAKE_PROFIT_READY');
    expect(result.finalCandidate?.takeProfitReadinessOnly, isTrue);
    expect(result.realOrderSubmitted, isFalse);
  });
}
