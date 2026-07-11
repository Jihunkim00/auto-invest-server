import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/broker_sync_watchdog.dart';

void main() {
  test('watchdog model parses healthy status', () {
    final result = BrokerSyncWatchdogResult.fromJson(
      brokerSyncWatchdogJson(),
    );

    expect(result.provider, 'kis');
    expect(result.market, 'KR');
    expect(result.healthy, isTrue);
    expect(result.automationBlockedBySync, isFalse);
    expect(result.canRunAutomation, isTrue);
    expect(result.staleLocalOrderCount, 0);
    expect(result.issues, isEmpty);
    expect(result.safetyFlags['broker_submit_called'], isFalse);
  });

  test('watchdog model parses unsafe issues and blockers', () {
    final result = BrokerSyncWatchdogResult.fromJson(
      brokerSyncWatchdogJson(
        syncHealth: 'unsafe',
        automationBlocked: true,
        staleLocalOrderCount: 1,
        pendingSyncOrderCount: 1,
        missingKisOdnoCount: 1,
        positionMismatchCount: 1,
        blockingReasons: const ['broker_sync_watchdog_blocked'],
        issues: const [
          {
            'issue_id': 'stale-1',
            'issue_type': 'stale_local_order',
            'severity': 'critical',
            'provider': 'kis',
            'market': 'KR',
            'symbol': '005930',
            'order_id': 42,
            'detected_at': '2026-07-10T01:05:00Z',
            'age_minutes': 18.5,
            'local_status': 'ACCEPTED',
            'automation_blocking': true,
            'recommended_action': 'manual_review',
            'reason': 'Local order has been open past the stale threshold.',
            'sanitized_context': {'source': 'unit_test'},
          },
          {
            'issue_id': 'position-1',
            'issue_type': 'position_quantity_mismatch',
            'severity': 'warning',
            'provider': 'kis',
            'market': 'KR',
            'symbol': '000660',
            'detected_at': '2026-07-10T01:06:00Z',
            'local_quantity': 2,
            'broker_quantity': 1,
            'automation_blocking': true,
            'recommended_action': 'inspect_broker_app',
            'reason': 'Position quantity differs between local and broker.',
            'sanitized_context': {},
          },
        ],
      ),
    );

    expect(result.unsafe, isTrue);
    expect(result.shouldBlockOrchestrator, isTrue);
    expect(result.blockingReasons, contains('broker_sync_watchdog_blocked'));
    expect(result.issues.first.issueType, 'stale_local_order');
    expect(result.issues.first.critical, isTrue);
    expect(result.issues.first.ageMinutes, 18.5);
    expect(result.issues.last.brokerQuantity, 1);
  });
}

Map<String, dynamic> brokerSyncWatchdogJson({
  String syncHealth = 'healthy',
  bool automationBlocked = false,
  int staleLocalOrderCount = 0,
  int pendingSyncOrderCount = 0,
  int missingBrokerIdCount = 0,
  int missingKisOdnoCount = 0,
  int brokerUnmatchedOrderCount = 0,
  int localUnmatchedOrderCount = 0,
  int stalePositionSnapshotCount = 0,
  int positionMismatchCount = 0,
  bool cashSnapshotStale = false,
  List<String> blockingReasons = const [],
  List<String> warningReasons = const [],
  List<Map<String, dynamic>> issues = const [],
}) {
  return {
    'run_id': automationBlocked ? 98 : 97,
    'generated_at': '2026-07-10T01:00:00Z',
    'provider': 'kis',
    'market': 'KR',
    'watchdog_enabled': false,
    'automation_blocked_by_sync': automationBlocked,
    'sync_health': syncHealth,
    'can_run_automation': !automationBlocked,
    'should_block_auto_buy': automationBlocked,
    'should_block_auto_sell': automationBlocked,
    'should_block_orchestrator': automationBlocked,
    'local_order_count': 3,
    'open_local_order_count': staleLocalOrderCount + pendingSyncOrderCount,
    'broker_open_order_count': brokerUnmatchedOrderCount,
    'stale_local_order_count': staleLocalOrderCount,
    'pending_sync_order_count': pendingSyncOrderCount,
    'missing_broker_id_count': missingBrokerIdCount,
    'missing_kis_odno_count': missingKisOdnoCount,
    'broker_unmatched_order_count': brokerUnmatchedOrderCount,
    'local_unmatched_order_count': localUnmatchedOrderCount,
    'stale_position_snapshot_count': stalePositionSnapshotCount,
    'position_mismatch_count': positionMismatchCount,
    'cash_snapshot_stale': cashSnapshotStale,
    'last_successful_sync_at': '2026-07-10T00:55:00Z',
    'last_watchdog_run_at': '2026-07-10T01:00:00Z',
    'issues': issues,
    'summary': automationBlocked ? 'Unsafe sync state.' : 'Sync is healthy.',
    'risk_flags': automationBlocked ? const ['sync_state_unsafe'] : const [],
    'gating_notes':
        automationBlocked ? const ['Broker sync review required.'] : const [],
    'blocking_reasons': blockingReasons,
    'warning_reasons': warningReasons,
    'next_safe_action':
        automationBlocked ? 'review_broker_sync_watchdog' : 'no_action',
    'safety_flags': const {
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'order_cancel_called': false,
    },
  };
}
