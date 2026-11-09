import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/home_latest_ai_decision_card.dart';
import 'package:auto_invest_dashboard/models/automation_today_decisions.dart';

void main() {
  test('execution blocker remains distinct from an AI score hold', () {
    final slot = AutomationTodayDecisionSlot.fromJson({
      'scheduler_slot': '13:30',
      'status': 'blocked',
      'reason': 'gpt_buy_score_below_threshold',
      'order_block_reason': 'unresolved_entry_limit_hit',
    });
    expect(slot.executionReasonCode, 'unresolved_entry_limit_hit');
    expect(slot.isAiScoreHold, isFalse);
  });
  const cases = {
    'unresolved_entry_limit_hit': '미완료 매수 주문이 신규 진입 한도를 점유하고 있습니다.',
    'position_state_refresh_pending': '보유 상태를 다시 확인한 후 이 슬롯의 분석을 재개합니다.',
    'position_retry_exit_unresolved': '청산 주문 또는 청산 재시도 확인이 끝나지 않아 매수를 차단했습니다.',
    'account_snapshot_unavailable': '계좌 조회를 완료하지 못해 매수를 차단했습니다.',
    'scheduler_task_timeout': '스케줄러 제한 시간 안에 작업이 끝나지 않았습니다.',
    'gpt_buy_score_below_threshold': 'AI 매수 점수가 기준에 미달해 매수를 보류했습니다.',
  };
  for (final entry in cases.entries) {
    testWidgets('home explains ${entry.key}', (tester) async {
      final controller = DashboardController(ApiClient(), autoload: false)
        ..todayAiDecisionsLoaded = true
        ..todayAiDecisions = AutomationTodayDecisions.fromJson({
          'trade_date_kst': '2026-11-09',
          'profile_id': 5,
          'slots': [
            {
              'scheduler_slot': '13:30',
              'status': entry.key == 'scheduler_task_timeout'
                  ? 'failed'
                  : entry.key == 'position_state_refresh_pending'
                      ? 'retry_pending'
                      : 'blocked',
              'reason': entry.key,
            },
          ],
        });
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: HomeLatestAiDecisionCard(controller: controller),
          ),
        ),
      ));
      expect(find.text(entry.value), findsOneWidget);
      expect(find.textContaining(entry.key), findsOneWidget);
      expect(find.text('포지션 또는 청산 확인이 완료되지 않아 매수를 차단했습니다.'), findsNothing);
      if (entry.key == 'gpt_buy_score_below_threshold') {
        expect(find.textContaining('13:30 · HOLD'), findsOneWidget);
        expect(find.text('AI 점수 미달 · 매수 보류'), findsOneWidget);
        expect(find.textContaining('13:30 · BLOCKED'), findsNothing);
      }
      expect(tester.takeException(), isNull);
      controller.dispose();
    });
  }
}
