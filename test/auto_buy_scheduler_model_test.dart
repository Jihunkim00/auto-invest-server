import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/strategy_auto_buy_scheduler.dart';

void main() {
  test('strategy auto buy scheduler model parses disabled state', () {
    final status = StrategyAutoBuySchedulerStatus.fromJson(
      autoBuySchedulerStatusJson(),
    );

    expect(status.enabled, isFalse);
    expect(status.provider, 'kis');
    expect(status.market, 'KR');
    expect(status.dryRunOnly, isTrue);
    expect(status.promotionQueueOnly, isTrue);
    expect(status.allowLiveOrders, isFalse);
    expect(status.realOrderSubmitAllowed, isFalse);
    expect(status.activeProfile, 'safe');
    expect(status.allowedProfiles, ['safe', 'balanced']);
    expect(status.runsToday, 1);
    expect(status.maxRunsPerDay, 3);
    expect(status.primaryBlockReason, 'scheduler_disabled');
    expect(status.pendingPromotionCount, 1);
    expect(status.scheduleSlots, ['09:10', '10:30', '14:30']);
    expect(status.safety['broker_submit_called'], isFalse);
  });

  test('strategy auto buy scheduler run result parses safety flags', () {
    final result = StrategyAutoBuySchedulerRunResult.fromJson({
      'status': 'ok',
      'action': 'would_buy',
      'provider': 'kis',
      'market': 'KR',
      'active_profile': 'safe',
      'created_promotion': true,
      'scheduler_run_id': 7,
      'real_order_submitted': false,
      'validation_called': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'promotion': {'id': 1, 'status': 'pending'},
      'dry_run_result': {'action': 'would_buy'},
      'safety': {'read_only': false},
    });

    expect(result.action, 'would_buy');
    expect(result.createdPromotion, isTrue);
    expect(result.realOrderSubmitted, isFalse);
    expect(result.validationCalled, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
    expect(result.manualSubmitCalled, isFalse);
    expect(result.schedulerRunId, 7);
  });
}

Map<String, dynamic> autoBuySchedulerStatusJson({
  bool enabled = false,
  String? blockReason = 'scheduler_disabled',
}) {
  return {
    'enabled': enabled,
    'provider': 'kis',
    'market': 'KR',
    'dry_run_only': true,
    'promotion_queue_only': true,
    'allow_live_orders': false,
    'real_order_submit_allowed': false,
    'active_profile': 'safe',
    'allowed_profiles': ['safe', 'balanced'],
    'runs_today': 1,
    'max_runs_per_day': 3,
    'next_allowed_run_at': '2026-06-26T02:00:00Z',
    'min_minutes_between_runs': 60,
    'market_open': true,
    'after_no_new_entry_time': false,
    'primary_block_reason': blockReason,
    'pending_promotion_count': 1,
    'latest_scheduler_run': {
      'id': 7,
      'result': 'blocked',
      'action': 'blocked',
      'block_reason': blockReason,
    },
    'schedule_slots': ['09:10', '10:30', '14:30'],
    'safety': {
      'read_only': true,
      'dry_run_only': true,
      'promotion_queue_only': true,
      'allow_live_orders': false,
      'real_order_submit_allowed': false,
      'validation_called': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'setting_changed': false,
      'scheduler_changed': false,
    },
  };
}
