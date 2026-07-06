import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/ops_production_readiness.dart';

void main() {
  test('production readiness model parses PR91 response', () {
    final readiness = OpsProductionReadiness.fromJson(readinessJson());

    expect(readiness.overallStatus, 'blocked');
    expect(readiness.readinessScore, 62);
    expect(readiness.summary.blockedCount, 2);
    expect(readiness.summary.warningCount, 3);
    expect(readiness.summary.canEnableSchedulerLiveOrders, isFalse);
    expect(readiness.summary.schedulerRealOrdersAllowed, isFalse);
    expect(readiness.summary.automationUnlockAllowed, isFalse);
    expect(readiness.blockingReasons, contains('dry_run_blocks_live_submit'));
    expect(readiness.nextSafeActions.single, contains('read-only'));
    expect(readiness.checklistItem('kill_switch_off')?.status, 'pass');
    expect(
        readiness.checklistItem('dry_run_blocks_live_submit')?.status, 'warn');
    expect(readiness.safetyFlags['read_only'], isTrue);
    expect(readiness.groupedChecklist.keys, contains('runtime'));
  });
}

Map<String, dynamic> readinessJson({String status = 'blocked'}) {
  return {
    'generated_at': '2026-07-06T09:00:00+09:00',
    'timezone': 'Asia/Seoul',
    'provider': 'kis',
    'market': 'KR',
    'overall_status': status,
    'readiness_score': 62,
    'summary': {
      'ready_count': 4,
      'warning_count': 3,
      'blocked_count': 2,
      'unknown_count': 1,
      'critical_block_count': 1,
      'can_use_guarded_live_buy': false,
      'can_use_guarded_live_sell': false,
      'can_enable_scheduler_live_orders': false,
      'scheduler_real_orders_allowed': false,
      'automation_unlock_allowed': false,
      'active_alert_count': 2,
      'sync_required_alert_count': 1,
    },
    'checklist': [
      {
        'key': 'kill_switch_off',
        'category': 'runtime',
        'status': 'pass',
        'title': 'Kill switch off',
        'detail': 'Kill switch is off.',
        'blocking': false,
        'severity': 'info',
        'related_type': null,
        'related_id': null,
        'next_safe_action': 'Review runtime settings.',
      },
      {
        'key': 'dry_run_blocks_live_submit',
        'category': 'runtime',
        'status': 'warn',
        'title': 'Dry-run live block',
        'detail': 'Dry-run is enabled.',
        'blocking': true,
        'severity': 'warning',
        'related_type': null,
        'related_id': null,
        'next_safe_action': 'Keep dry-run on.',
      },
      {
        'key': 'scheduler_real_orders_allowed',
        'category': 'scheduler',
        'status': 'pass',
        'title': 'Scheduler real orders disabled',
        'detail': 'Scheduler real orders are not allowed.',
        'blocking': false,
        'severity': 'info',
        'related_type': null,
        'related_id': null,
        'next_safe_action': 'Keep scheduler live orders disabled.',
      },
      {
        'key': 'active_alert_count',
        'category': 'alerts',
        'status': 'warn',
        'title': 'Active alerts',
        'detail': 'Active alerts: 2.',
        'blocking': false,
        'severity': 'warning',
        'related_type': null,
        'related_id': null,
        'next_safe_action': 'Review operator alerts.',
      },
    ],
    'blocking_reasons': ['dry_run_blocks_live_submit'],
    'warnings': ['active_alert_count'],
    'next_safe_actions': [
      'Keep this report read-only; use existing explicit controls.',
    ],
    'safety_flags': {
      'read_only': true,
      'no_live_orders': true,
      'broker_submit_called': false,
      'settings_changed': false,
      'scheduler_changed': false,
      'automation_unlock_allowed': false,
    },
    'details': {
      'orders': {'pending_sync_count': 1},
      'alerts': {'active_alert_count': 2},
    },
  };
}
