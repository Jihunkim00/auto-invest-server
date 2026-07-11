import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/automation_mode_control.dart';

void main() {
  test('automation mode model parses safe default off status', () {
    final status = AutomationModeControlStatus.fromJson(
      automationModeStatusJson(),
    );

    expect(status.automationMode, 'off');
    expect(status.modeLabel, 'Automation Off');
    expect(status.effectiveStatus, 'off');
    expect(status.canSubmitLiveOrder, isFalse);
    expect(status.dryRun, isTrue);
    expect(status.killSwitch, isFalse);
    expect(status.kisRealOrderEnabled, isFalse);
    expect(status.blockingReasons, contains('automation_mode_off'));
    expect(status.brokerSyncHealth, 'healthy');
    expect(status.brokerSyncIssueCount, 0);
    expect(status.safetyFlags['broker_submit_called'], isFalse);
    expect(status.safetyFlags['real_order_submitted'], isFalse);
  });

  test('automation mode model parses phase1 blocked gates and blockers', () {
    final status = AutomationModeControlStatus.fromJson(
      automationModeStatusJson(
        mode: 'phase1_live_ready',
        label: 'Phase 1 Live Ready',
        effectiveStatus: 'live_ready_blocked',
        blockingReasons: const [
          'dry_run_enabled',
          'sync_required_order_exists'
        ],
        warningReasons: const ['dry_run_is_separate'],
        brokerSyncHealth: 'unsafe',
        brokerSyncBlockingReasons: const ['broker_sync_watchdog_blocked'],
        brokerSyncIssueCount: 1,
        pendingOrderBlockers: const [
          {
            'order_id': 42,
            'symbol': '005930',
            'side': 'buy',
            'internal_status': 'SYNC_FAILED',
            'sync_required': true,
            'reason': 'sync_required',
          },
        ],
      ),
    );

    expect(status.liveBlocked, isTrue);
    expect(status.brokerSyncHealth, 'unsafe');
    expect(status.brokerSyncBlockingReasons,
        contains('broker_sync_watchdog_blocked'));
    expect(status.brokerSyncIssueCount, 1);
    expect(status.pendingOrderBlockers.single.orderId, 42);
    expect(status.pendingOrderBlockers.single.syncRequired, isTrue);
    expect(status.warningReasons, contains('dry_run_is_separate'));
  });
}

Map<String, dynamic> automationModeStatusJson({
  String mode = 'off',
  String label = 'Automation Off',
  String effectiveStatus = 'off',
  List<String> blockingReasons = const ['automation_mode_off'],
  List<String> warningReasons = const [],
  List<Map<String, dynamic>> pendingOrderBlockers = const [],
  bool canSubmitLiveOrder = false,
  bool dryRun = true,
  bool killSwitch = false,
  bool kisRealOrderEnabled = false,
  String brokerSyncHealth = 'healthy',
  List<String> brokerSyncBlockingReasons = const [],
  int brokerSyncIssueCount = 0,
}) {
  return {
    'generated_at': '2026-07-10T00:00:00Z',
    'automation_mode': mode,
    'mode_label': label,
    'mode_description': 'Mode description',
    'mode_updated_at': '2026-07-10T00:01:00Z',
    'mode_updated_by': 'api',
    'mode_reason': 'test',
    'mode_requires_manual_review': true,
    'effective_status': effectiveStatus,
    'can_run_monitoring': mode != 'off',
    'can_run_dry_run': mode == 'dry_run_auto',
    'can_attempt_phase1_live': canSubmitLiveOrder,
    'can_submit_live_order': canSubmitLiveOrder,
    'kill_switch': killSwitch,
    'dry_run': dryRun,
    'kis_enabled': kisRealOrderEnabled,
    'kis_real_order_enabled': kisRealOrderEnabled,
    'production_readiness_status': 'blocked',
    'broker_sync_health': brokerSyncHealth,
    'broker_sync_blocking_reasons': brokerSyncBlockingReasons,
    'broker_sync_issue_count': brokerSyncIssueCount,
    'broker_sync_watchdog': {
      'sync_health': brokerSyncHealth,
      'issue_count': brokerSyncIssueCount,
    },
    'portfolio_orchestrator_enabled': mode != 'off',
    'portfolio_orchestrator_allow_live_orders': mode == 'phase1_live_ready',
    'position_management_scheduler_enabled':
        mode == 'dry_run_auto' || mode == 'phase1_live_ready',
    'auto_buy_live_phase1_enabled': mode == 'phase1_live_ready',
    'auto_sell_live_phase1_enabled': mode == 'phase1_live_ready',
    'scheduler_enabled': mode == 'dry_run_auto' || mode == 'phase1_live_ready',
    'pending_order_blockers': pendingOrderBlockers,
    'sync_required_count': pendingOrderBlockers.length,
    'critical_exit_candidate_count': 0,
    'daily_trade_limit_remaining': canSubmitLiveOrder ? 1 : 0,
    'blocking_reasons': blockingReasons,
    'warning_reasons': warningReasons,
    'next_safe_action': mode == 'off'
        ? 'automation_is_off'
        : 'review_dry_run_setting_without_changing_it_here',
    'safety_flags': {
      'control_center_only': true,
      'settings_changed_only': true,
      'orders_mutated': false,
      'order_log_created': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'real_order_submitted': false,
      'dry_run_changed': false,
      'kill_switch_changed': false,
      'kis_real_order_enabled_changed': false,
    },
    'modules': {
      'portfolio_orchestrator': {
        'enabled': mode != 'off',
        'allow_live_orders': mode == 'phase1_live_ready',
      },
    },
  };
}
