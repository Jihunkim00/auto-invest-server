import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/position_management_dry_run.dart';

void main() {
  test('position management dry-run model parses safety and candidates', () {
    final result = PositionManagementDryRun.fromJson(_runJson());

    expect(result.runId, 42);
    expect(result.dryRunOnly, isTrue);
    expect(result.realOrderSubmitted, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
    expect(result.manualSubmitCalled, isFalse);
    expect(result.positionsChecked, 1);
    expect(result.exitCandidateCount, 1);
    expect(result.criticalCandidateCount, 1);
    expect(result.simulatedSellPreflightCount, 1);
    expect(result.priority, 'positions_first');
    expect(result.entryOrdersAllowed, isFalse);
    expect(result.exitOrdersAllowed, isFalse);
    expect(result.dryRunMonitoringOnly, isTrue);
    expect(result.candidates.single.candidateType, 'stop_loss');
    expect(result.sellPreflightResults.single['preflight_status'], 'allowed');
    expect(result.nextSafeActions, contains('Review candidates.'));
  });
}

Map<String, dynamic> _runJson() {
  return {
    'run_id': 42,
    'generated_at': '2026-07-07T09:00:00Z',
    'provider': 'kis',
    'market': 'KR',
    'trigger_source': 'manual_position_management_dry_run',
    'dry_run_only': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'positions_checked': 1,
    'exit_candidate_count': 1,
    'critical_candidate_count': 1,
    'warning_candidate_count': 0,
    'simulated_sell_preflight_count': 1,
    'blocked_preflight_count': 0,
    'sync_required_count': 0,
    'duplicate_sell_conflict_count': 0,
    'result_status': 'completed',
    'primary_reason': 'position_management_dry_run_completed',
    'risk_flags': const ['dry_run_only'],
    'gating_notes': const ['No order path was called.'],
    'candidates': [_candidate()],
    'sell_preflight_results': const [
      {'symbol': '005930', 'preflight_status': 'allowed'},
    ],
    'next_safe_actions': const ['Review candidates.'],
    'priority': 'positions_first',
    'entry_orders_allowed': false,
    'exit_orders_allowed': false,
    'dry_run_monitoring_only': true,
    'scheduler_enabled': false,
    'scheduler_dry_run_only': true,
    'scheduler_allow_live_orders': false,
    'safety': const {'dry_run_only': true},
  };
}

Map<String, dynamic> _candidate() {
  return {
    'candidate_id': 'auto-exit:kis:KR:005930:stop_loss:20260707',
    'symbol': '005930',
    'provider': 'kis',
    'market': 'KR',
    'candidate_type': 'stop_loss',
    'severity': 'critical',
    'status': 'active',
    'action_hint': 'run_sell_preflight',
    'position_quantity': 3,
    'available_quantity': 3,
    'average_price': 10000,
    'current_price': 9000,
    'cost_basis': 30000,
    'current_value': 27000,
    'unrealized_pl': -3000,
    'unrealized_pl_pct': -0.10,
    'stop_loss_threshold_pct': 2,
    'take_profit_threshold_pct': 3,
    'stop_loss_triggered': true,
    'take_profit_triggered': false,
    'trend_breakdown_triggered': false,
    'risk_flags': const ['stop_loss_triggered'],
    'gating_notes': const ['Read-only candidate detection.'],
    'primary_reason': 'Stop-loss threshold was reached.',
    'next_safe_action': 'Run sell preflight.',
    'open_sell_order_conflict': false,
    'sync_required': false,
    'can_run_sell_preflight': true,
  };
}
