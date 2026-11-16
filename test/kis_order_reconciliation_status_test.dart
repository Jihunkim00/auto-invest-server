import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/kis_order_reconciliation_status.dart';
import 'package:auto_invest_dashboard/models/automation_today_decisions.dart';

void main() {
  testWidgets('current warning clears after terminal evidence while counters remain', (tester) async {
    Future<void> render(Map<String, dynamic> status) => tester.pumpWidget(
      MaterialApp(home: Scaffold(body: KisOrderReconciliationStatus(status: status))),
    );
    const warning = '이전 매도 주문의 최종 상태를 확인 중이어서 신규 매수를 보류했습니다.';
    await render({
      'unresolved_count': 2, 'checked_count': 2, 'manual_review_count': 1,
      'last_synced_at': '2026-11-16T09:30:00+09:00',
      'buy_hold_message': warning, 'last_failure_reason': 'history_incomplete',
    });
    expect(find.text(warning), findsOneWidget);
    expect(find.byKey(const ValueKey('kis-order-reconciliation-failure')), findsOneWidget);
    expect(find.textContaining('(KST 09:30)'), findsOneWidget);
    await render({'unresolved_count': 0, 'checked_count': 2, 'finalized_count': 2,
      'buy_hold_message': warning, 'last_failure_reason': 'old_failure'});
    expect(find.text(warning), findsNothing);
    expect(find.byKey(const ValueKey('kis-order-reconciliation-failure')), findsNothing);
    expect(find.textContaining('종료 2'), findsOneWidget);
  });

  test('today feed accepts optional account reconciliation', () {
    expect(AutomationTodayDecisions.fromJson({}).orderReconciliation, isNull);
    final feed = AutomationTodayDecisions.fromJson({
      'order_reconciliation': {'unresolved_count': 2, 'timezone': 'Asia/Seoul'},
    });
    expect(feed.orderReconciliation?['unresolved_count'], 2);
  });
}
