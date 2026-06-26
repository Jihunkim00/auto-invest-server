import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/strategy_auto_buy_operations.dart';

void main() {
  test('strategy auto buy operations model parses nested status', () {
    final status = StrategyAutoBuyOperationsStatus.fromJson(
      autoBuyOperationsJson(),
    );

    expect(status.provider, 'kis');
    expect(status.market, 'KR');
    expect(status.activeProfile, 'safe');
    expect(status.autoBuyStage, 'ready_for_operator_confirm');
    expect(status.nextOperatorAction, 'confirm_guarded_live_buy');
    expect(status.readyForOperatorConfirm, isTrue);
    expect(status.dryRun.recentFound, isTrue);
    expect(status.dryRun.latestAction, 'would_buy');
    expect(status.dryRun.latestSymbol, '005930');
    expect(status.dryRun.latestScore, 80);
    expect(status.dryRun.wouldBuyCountToday, 1);
    expect(status.liveReadiness.ready, isTrue);
    expect(status.liveReadiness.ordersRemainingToday, 1);
    expect(status.liveAttempts.latestStatus, 'blocked');
    expect(status.liveAttempts.recent, hasLength(1));
    expect(status.risk.entryAllowed, isTrue);
    expect(status.risk.targetProgressPct, 32.5);
    expect(status.safety['read_only'], isTrue);
    expect(status.safety['broker_submit_called'], isFalse);
  });
}

Map<String, dynamic> autoBuyOperationsJson({
  String stage = 'ready_for_operator_confirm',
  String nextAction = 'confirm_guarded_live_buy',
  bool ready = true,
}) {
  return {
    'provider': 'kis',
    'market': 'KR',
    'active_profile': 'safe',
    'auto_buy_stage': stage,
    'next_operator_action': nextAction,
    'dry_run': {
      'recent_found': true,
      'latest_action': 'would_buy',
      'latest_symbol': '005930',
      'latest_score': 80,
      'latest_time': '2026-06-26T01:00:00Z',
      'would_buy_count_today': 1,
      'blocked_count_today': 0,
      'summary': {'total': 1, 'would_buy': 1},
    },
    'live_readiness': {
      'ready': ready,
      'enabled': true,
      'primary_block_reason': ready ? null : 'target_risk_rejected',
      'recent_dry_run_required': true,
      'recent_dry_run_found': true,
      'dry_run_status': 'would_buy',
      'kill_switch': false,
      'kis_real_order_enabled': true,
      'target_risk_ready': ready,
      'orders_remaining_today': ready ? 1 : 0,
    },
    'live_attempts': {
      'latest_status': 'blocked',
      'submitted_count_today': 0,
      'blocked_count_today': 1,
      'sync_required_count': 0,
      'recent': [
        {
          'attempt_id': 1,
          'status': 'blocked',
          'symbol': '005930',
          'block_reason': 'target_risk_rejected',
        }
      ],
    },
    'risk': {
      'entry_allowed': ready,
      'size_multiplier': 1.0,
      'target_progress_pct': 32.5,
      'daily_loss_limit_hit': false,
      'monthly_loss_limit_hit': false,
    },
    'safety': {
      'read_only': true,
      'validation_called': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'setting_changed': false,
      'scheduler_changed': false,
    },
  };
}
