import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/operator_alerts.dart';

void main() {
  test('operator alerts model parses nested read-only payload', () {
    final alerts = OperatorAlerts.fromJson(operatorAlertsJson());

    expect(alerts.provider, 'kis');
    expect(alerts.market, 'KR');
    expect(alerts.summary.activeAlertCount, 3);
    expect(alerts.summary.criticalCount, 1);
    expect(alerts.summary.syncRequiredCount, 1);
    expect(alerts.summary.rejectedOrderCount, 1);
    expect(alerts.alerts, hasLength(3));
    expect(alerts.alerts.first.alertId, 'pr89:kis:KR:risk_gate:duplicate');
    expect(alerts.alerts.first.isCritical, isTrue);
    expect(alerts.alerts[1].riskFlags, contains('sync_required'));
    expect(alerts.nextSafeActions.first, contains('Review'));
    expect(alerts.isReadOnly, isTrue);
  });
}

Map<String, dynamic> operatorAlertsJson({
  String provider = 'kis',
  String market = 'KR',
  int activeAlertCount = 3,
  List<Map<String, dynamic>>? alerts,
}) {
  final items =
      alerts ?? _operatorAlertItems(provider: provider, market: market);
  return {
    'generated_at': '2026-07-05T01:30:00Z',
    'timezone': 'Asia/Seoul',
    'provider': provider,
    'market': market,
    'summary': {
      'active_alert_count': activeAlertCount,
      'critical_count':
          items.where((item) => item['severity'] == 'critical').length,
      'warning_count':
          items.where((item) => item['severity'] == 'warning').length,
      'info_count': items.where((item) => item['severity'] == 'info').length,
      'sync_required_count': 1,
      'rejected_order_count': 1,
      'blocked_attempt_count': 0,
      'stale_promotion_count': 1,
      'incomplete_pl_count': 1,
      'runtime_warning_count': 0,
    },
    'alerts': items,
    'next_safe_actions': const [
      'Review local orders and broker status.',
      'Use explicit sync controls outside this alert center only after review.',
    ],
    'safety_flags': const {
      'read_only': true,
      'no_live_orders': true,
      'scheduler_dry_run_only': true,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'validation_called': false,
      'sync_called': false,
      'setting_changed': false,
      'scheduler_changed': false,
      'order_state_mutated': false,
    },
  };
}

List<Map<String, dynamic>> _operatorAlertItems({
  required String provider,
  required String market,
}) {
  return [
    {
      'alert_id': 'pr89:kis:KR:risk_gate:duplicate',
      'severity': 'critical',
      'category': 'risk_gate',
      'status': 'active',
      'title': 'Duplicate open order risk',
      'message': 'Multiple open orders exist for 005930.',
      'provider': provider,
      'market': market,
      'symbol': '005930',
      'related_type': 'order_group',
      'related_id': '005930:buy',
      'created_at': '2026-07-05T01:00:00Z',
      'updated_at': '2026-07-05T01:10:00Z',
      'source': 'orders',
      'reason_code': 'duplicate_open_order_risk',
      'risk_flags': ['duplicate_open_order_risk'],
      'gating_notes': ['open_order_count=2'],
      'next_safe_action': 'Review open orders for the symbol.',
      'is_actionable': true,
      'action_type': 'open_order_detail',
    },
    {
      'alert_id': 'pr89:kis:KR:order:sync',
      'severity': 'warning',
      'category': 'order',
      'status': 'active',
      'title': 'Order status sync required',
      'message': '000660 order needs explicit status review.',
      'provider': provider,
      'market': market,
      'symbol': '000660',
      'related_type': 'order',
      'related_id': 12,
      'created_at': '2026-07-05T01:00:00Z',
      'updated_at': '2026-07-05T01:05:00Z',
      'source': 'orders',
      'reason_code': 'order_sync_required',
      'risk_flags': ['sync_required'],
      'gating_notes': ['last_sync_missing_or_old'],
      'next_safe_action': 'Review order details before explicit sync.',
      'is_actionable': true,
      'action_type': 'open_order_detail',
    },
    {
      'alert_id': 'pr89:kis:KR:pnl:incomplete',
      'severity': 'info',
      'category': 'pnl',
      'status': 'active',
      'title': 'P/L calculation incomplete',
      'message': 'One calculation item is incomplete.',
      'provider': provider,
      'market': market,
      'symbol': null,
      'related_type': 'daily_ops_summary',
      'related_id': '2026-07-05',
      'created_at': '2026-07-05T01:00:00Z',
      'updated_at': '2026-07-05T01:05:00Z',
      'source': 'daily_ops_summary',
      'reason_code': 'incomplete_pl_calculation',
      'risk_flags': ['missing_fill_price'],
      'gating_notes': ['local_order_logs_and_cached_snapshots'],
      'next_safe_action': 'Review lifecycle details.',
      'is_actionable': true,
      'action_type': 'open_daily_summary',
    },
  ];
}
