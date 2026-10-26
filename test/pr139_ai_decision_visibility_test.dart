import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/home_latest_ai_decision_card.dart';
import 'package:auto_invest_dashboard/models/automation_today_decisions.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';

Map<String, dynamic> _hold() => {
      'scheduler_slot': '12:30',
      'status': 'analysis_complete',
      'action': 'hold',
      'gpt_completed_symbols': ['263750'],
      'gpt_target_symbols': ['263750'],
      'final_ranked_top5': [],
      'analysis_candidates': [
        {
          'symbol': '263750',
          'symbol_name': '펄어비스',
          'gpt_analysis_status': 'completed',
          'gpt_buy_score': 52,
          'final_buy_score': 62.01,
          'block_reason': 'gpt_buy_score_below_threshold',
        }
      ],
    };

AutomationTodayDecisions _feed(List<Map<String, dynamic>> slots,
        {List<Map<String, dynamic>> history = const []}) =>
    AutomationTodayDecisions.fromJson({
      'profile_id': 8,
      'owner_user_id': 2,
      'trade_date_kst': '2026-10-26',
      'slots': slots,
      'execution_history': history,
    });

Future<void> _show(WidgetTester tester, DashboardController controller) =>
    tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: HomeLatestAiDecisionCard(
              controller: controller, userScoped: true),
        ),
      ),
    ));

void main() {
  testWidgets('C score HOLD clearly labels GPT as not run', (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..todayAiDecisionsLoaded = true
      ..todayAiDecisions = _feed([
        {
          'scheduler_slot': '11:30',
          'status': 'analysis_complete',
          'action': 'hold',
          'reason': 'c_quant_score_below_threshold',
          'analysis_candidates': [
            {
              'symbol': '005930',
              'quant_c_score': 64.55,
              'gpt_used': false,
              'gpt_analysis_status': 'not_run',
            }
          ],
        }
      ]);
    addTearDown(controller.dispose);
    await _show(tester, controller);
    expect(find.textContaining('11:30 · HOLD'), findsOneWidget);
    expect(find.text('C 기준 정량 통과 후보 없음 · GPT 분석 미실행'), findsOneWidget);
    expect(find.text('후보 분석 결과'), findsOneWidget);
    expect(find.text('GPT 분석 결과'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('home-ai-score-gates-11:30')));
    await tester.pumpAndSettle();
    expect(find.textContaining('C 64.5'), findsOneWidget);
    expect(
        controller
            .todayAiDecisions.slots.single.auditCandidates.single.quantCScore,
        64.55);
    expect(find.textContaining('GPT 0'), findsNothing);
    expect(find.textContaining('Final 0'), findsNothing);
  });

  testWidgets('completed GPT HOLD falls back to audit without final candidates',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..todayAiDecisionsLoaded = true
      ..todayAiDecisions = _feed([_hold()]);
    addTearDown(controller.dispose);
    await _show(tester, controller);
    expect(find.textContaining('12:30 · HOLD'), findsOneWidget);
    expect(find.textContaining('263750'), findsOneWidget);
    expect(find.textContaining('GPT completed'), findsOneWidget);
    expect(find.textContaining('GPT 52'), findsOneWidget);
    expect(find.textContaining('Final Buy 62.01'), findsOneWidget);
    expect(
        find.textContaining('gpt_buy_score_below_threshold'), findsOneWidget);
    expect(find.text('최종 Top5'), findsNothing);
    expect(find.text('GPT 분석 결과'), findsOneWidget);
    expect(find.text('분석 결과 없음'), findsNothing);
    expect(controller.todayAiDecisions.slots.single.isQuantHold, isFalse);
  });

  testWidgets('old failed execution stays separate from unexecuted new slot',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..todayAiDecisionsLoaded = true
      ..todayAiDecisions = _feed([
        {'scheduler_slot': '13:45', 'status': 'no_result'},
      ], history: [
        {
          'scheduler_slot': '13:30',
          'status': 'failed',
          'reason': 'account_snapshot_retry_exhausted',
          'failure_stage': 'account_snapshot',
          'http_status': 500,
        },
      ]);
    addTearDown(controller.dispose);
    await _show(tester, controller);
    expect(find.textContaining('13:30 · FAILED'), findsOneWidget);
    expect(find.textContaining('13:45 · 분석 결과 없음'), findsOneWidget);
    expect(find.text('이전 슬롯 실행 이력'), findsOneWidget);
    expect(find.text('account_snapshot_retry_exhausted'), findsOneWidget);
    expect(find.text('계좌 조회 실패 · HTTP 500'), findsOneWidget);
  });

  testWidgets(
      'API error ends loading and refresh replaces it with server result',
      (tester) async {
    final api = _TodayApi()..fail = true;
    final controller = DashboardController(api, autoload: false);
    addTearDown(controller.dispose);
    await controller.loadUserHomeRecentActivity();
    await _show(tester, controller);
    await tester.pumpAndSettle();
    expect(controller.todayAiDecisionsLoaded, isTrue);
    expect(find.text('오늘 AI 판단을 불러오지 못했습니다.'), findsOneWidget);
    expect(find.text('오늘의 슬롯 분석 결과를 불러오는 중...'), findsNothing);
    api.fail = false;
    await controller.loadUserHomeRecentActivity();
    await _show(tester, controller);
    await tester.pumpAndSettle();
    expect(find.textContaining('GPT 52'), findsOneWidget);
    expect(find.text('오늘 AI 판단을 불러오지 못했습니다.'), findsNothing);
    expect(api.adminCalls, 0);
  });

  test('later refresh wins over an older response', () async {
    final first = Completer<AutomationTodayDecisions>();
    final second = Completer<AutomationTodayDecisions>();
    final api = _TodayApi()..pending.addAll([first, second]);
    final controller = DashboardController(api, autoload: false);
    addTearDown(controller.dispose);
    await controller.loadUserHomeRecentActivity();
    await controller.loadUserHomeRecentActivity();
    second.complete(_feed([_hold()]));
    await Future<void>.delayed(Duration.zero);
    first.complete(AutomationTodayDecisions.empty);
    await Future<void>.delayed(Duration.zero);
    expect(controller.todayAiDecisions.slots.single.symbol, '263750');
  });

  test('previous account response cannot populate a replacement session',
      () async {
    final pending = Completer<AutomationTodayDecisions>();
    final api = _TodayApi()..pending.add(pending);
    final previous = DashboardController(api, autoload: false);
    await previous.loadUserHomeRecentActivity();
    final current = previous.clearAuthenticatedSession();
    addTearDown(previous.dispose);
    addTearDown(current.dispose);
    pending.complete(_feed([_hold()]));
    await Future<void>.delayed(Duration.zero);
    expect(current.todayAiDecisions.slots, isEmpty);
    expect(previous.todayAiDecisions.slots, isEmpty);
  });
}

class _TodayApi extends ApiClient {
  bool fail = false;
  int adminCalls = 0;
  final pending = <Completer<AutomationTodayDecisions>>[];

  @override
  Future<List<TradingLogItem>> fetchUserTradingRuns({int limit = 50}) async =>
      [];

  @override
  Future<AutomationTodayDecisions> fetchUserTodayAiDecisions() async {
    if (pending.isNotEmpty) return pending.removeAt(0).future;
    if (fail) throw StateError('fake API failure');
    return _feed([_hold()]);
  }

  @override
  Future<AutomationTodayDecisions> fetchAdminTodayAiDecisions() async {
    adminCalls++;
    return AutomationTodayDecisions.empty;
  }
}
