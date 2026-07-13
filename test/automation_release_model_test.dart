import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/automation_release.dart';

void main() {
  test('release status parses checklist and safety fields', () {
    final status =
        AutomationReleaseStatus.fromJson(automationReleaseStatusJson());

    expect(status.releaseEnabled, isTrue);
    expect(status.effectiveStatus, 'live_ready_blocked');
    expect(status.canRunMonitoringCycle, isTrue);
    expect(status.canSubmitLiveOrder, isFalse);
    expect(status.dailyTradeLimitRemaining, 2);
    expect(status.checklist, hasLength(2));
    expect(status.checklist.first.key, 'release_enabled');
    expect(status.safetyFlags['direct_broker_submit_path'], isFalse);
  });

  test('release cycle parses no broker submit and no order cancel flags', () {
    final result =
        AutomationReleaseCycleResult.fromJson(automationReleaseCycleJson());

    expect(result.resultStatus, 'dry_run_completed');
    expect(result.completed, isTrue);
    expect(result.realOrderSubmitted, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
    expect(result.orderCancelCalled, isFalse);
    expect(result.soakRunId, 11);
  });
}

Map<String, dynamic> automationReleaseStatusJson({
  bool releaseEnabled = true,
  String effectiveStatus = 'live_ready_blocked',
  bool canSubmitLiveOrder = false,
  List<String> blockingReasons = const ['dry_run_enabled'],
}) {
  return {
    'generated_at': '2026-07-13T00:00:00Z',
    'release_enabled': releaseEnabled,
    'release_mode': 'controlled_phase1',
    'release_armed': releaseEnabled,
    'release_armed_at': '2026-07-13T00:00:00Z',
    'release_reason': 'test release',
    'effective_status': effectiveStatus,
    'can_run_monitoring_cycle': true,
    'can_run_dry_run_cycle': true,
    'can_run_live_phase1_cycle': canSubmitLiveOrder,
    'can_submit_live_order': canSubmitLiveOrder,
    'automation_mode_status': const {'automation_mode': 'phase1_live_ready'},
    'broker_sync_status': const {'sync_health': 'healthy'},
    'soak_status': const {'effective_status': 'dry_run_ready'},
    'kill_latch_active': false,
    'production_readiness_status': 'ready',
    'orchestrator_status': const {'result_status': 'completed_no_action'},
    'auto_buy_phase1_status': const {'result_status': 'skipped'},
    'auto_sell_phase1_status': const {'result_status': 'skipped'},
    'daily_trade_limit_remaining': 2,
    'daily_auto_buy_remaining': 1,
    'daily_auto_sell_remaining': 1,
    'blocking_reasons': blockingReasons,
    'warning_reasons': const ['dry_run_is_separate'],
    'checklist': [
      {
        'key': 'release_enabled',
        'label': 'Release enabled',
        'passed': releaseEnabled,
        'severity': 'critical',
        'reason': releaseEnabled ? null : 'automation_release_disabled',
        'blocking': true,
        'next_action': releaseEnabled ? 'no_action' : 'arm_release',
      },
      {
        'key': 'dry_run_off_for_live',
        'label': 'Dry-run off for live',
        'passed': false,
        'severity': 'critical',
        'reason': 'dry_run_enabled',
        'blocking': true,
        'next_action': 'operator_must_change_dry_run_outside_release',
      },
    ],
    'safety_flags': const {
      'direct_broker_submit_path': false,
      'order_cancel_path': false,
      'release_does_not_change_dry_run': true,
    },
    'next_safe_action': 'operator_must_change_dry_run_outside_release',
  };
}

Map<String, dynamic> automationReleaseCycleJson({
  String resultStatus = 'dry_run_completed',
}) {
  return {
    'run_id': 7,
    'generated_at': '2026-07-13T00:01:00Z',
    'release_enabled': true,
    'release_mode': 'controlled_phase1',
    'cycle_mode': 'dry_run',
    'result_status': resultStatus,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'order_cancel_called': false,
    'action_taken': 'none',
    'orchestrator_run_id': 10,
    'soak_run_id': 11,
    'checklist': automationReleaseStatusJson()['checklist'],
    'blocking_reasons': const [],
    'warning_reasons': const [],
    'risk_flags': const [],
    'gating_notes': const ['release delegated to soak'],
    'next_safe_action': 'review_release_cycle_result',
    'safety_flags': const {
      'direct_broker_submit_path': false,
      'order_cancel_path': false,
    },
  };
}
