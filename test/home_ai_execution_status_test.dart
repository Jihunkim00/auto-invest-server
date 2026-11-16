import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/home_latest_ai_decision_card.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/automation_today_decisions.dart';

const reason = 'calendar_gap_c_below_threshold';

Map<String, dynamic> esoneSlot() => {
      'scheduler_slot': '11:10',
      'trade_date_kst': '2026-11-13',
      'owner_user_id': 1,
      'profile_id': 5,
      'status': 'blocked',
      'analysis_status': 'result',
      'analysis_execution_status': 'LIVE_READY',
      'analysis_reason': 'target_aware_risk_approved',
      'signal_status': 'LIVE_READY',
      'scheduler_status': 'blocked',
      'scheduler_outcome_applied': true,
      'execution_status': 'blocked',
      'execution_reason': reason,
      'reason': 'target_aware_risk_approved',
      'symbol': '012750',
      'symbol_name': '에스원',
      'final_selected_symbol': '012750',
      'final_buy_score': 72.45,
      'broker_submit_called': false,
      'real_order_submitted': false,
      'order_status': 'NOT SUBMITTED',
      'calendar_gap_risk': {
        'pre_market_closure_risk': true,
        'required_c_score': 75.0,
        'required_final_score': 70.0,
      },
      'calendar_gap_candidate_diagnostics': [
        {'symbol': '005930', 'quant_c_score': 99, 'final_buy_score': 99},
        {
          'symbol': '012750',
          'quant_c_score': 74.94,
          'quant_c_threshold': 65.0,
          'final_buy_score': 72.45,
          'skip_reason': reason,
        },
      ],
      'analysis_candidates': [
        {
          'symbol': '012750',
          'name': '에스원',
          'quant_buy_score': 62,
          'gpt_analysis_status': 'completed',
          'gpt_buy_score': 65.0,
          'final_buy_score': 72.45,
          'final_selected': true,
        },
      ],
    };

AutomationTodayDecisions feed(List<Map<String, dynamic>> slots,
        {String day = '2026-11-13', int owner = 1, int profile = 5}) =>
    AutomationTodayDecisions.fromJson({
      'trade_date_kst': day,
      'owner_user_id': owner,
      'profile_id': profile,
      'slots': slots,
    });

Future<DashboardController> showFeed(
    WidgetTester tester, AutomationTodayDecisions decisions) async {
  final controller = DashboardController(ApiClient(), autoload: false)
    ..todayAiDecisions = decisions
    ..todayAiDecisionsLoaded = true;
  addTearDown(controller.dispose);
  await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
          body: SingleChildScrollView(
              child: HomeLatestAiDecisionCard(controller: controller)))));
  return controller;
}

void main() {
  for (final entry in {
    'calendar_gap_final_below_threshold':
        '주말 전 강화된 최종 점수 기준을 충족하지 못해 매수하지 않았습니다.',
    'calendar_gap_risk_unavailable': '거래일·휴장 위험 정보를 확인할 수 없어 매수하지 않았습니다.',
    'weekend_gap_late_entry_block': '주말 전 신규 진입 마감으로 매수하지 않았습니다.',
    'position_management_priority': '포지션 관리 우선으로 신규 매수를 차단했습니다.',
  }.entries) {
    testWidgets('execution explanation: ${entry.key}', (tester) async {
      final slot = esoneSlot()..['execution_reason'] = entry.key;
      await showFeed(tester, feed([slot]));
      expect(find.text(entry.value), findsOneWidget);
      expect(find.text('AI 분석: 통과'), findsOneWidget);
      expect(find.text('실제 매수: 차단'), findsOneWidget);
    });
  }

  testWidgets('canonical block stays primary even with a linked order record',
      (tester) async {
    final slot = esoneSlot()..['order_status'] = 'BROKER SUBMITTED';
    await showFeed(tester, feed([slot]));
    expect(find.text('실제 매수: 차단'), findsOneWidget);
    expect(find.text('실제 매수: 매수 제출'), findsNothing);
  });

  test(
      'A: canonical block takes priority while analysis and C scores stay separate',
      () {
    final slot = feed([esoneSlot()]).slots.single;
    expect(slot.analysisPassed, isTrue);
    expect(slot.executionBlocked, isTrue);
    expect(slot.executionReasonCode, reason);
    expect(slot.quantCScore, 74.94);
    expect(slot.requiredCScore, 75);
    expect(slot.requiredFinalScore, 70);
    expect(slot.gptBuyScore, 65);
    expect(slot.orderSubmitted, isFalse);
    expect(slot.fillConfirmed, isFalse);
  });

  testWidgets(
      'A: Esone shows passed analysis and blocked BUY with applied scores',
      (tester) async {
    await showFeed(tester, feed([esoneSlot()]));
    expect(find.text('AI 분석: 통과'), findsOneWidget);
    expect(find.text('실제 매수: 차단'), findsOneWidget);
    expect(find.text('에스원 (012750)'), findsOneWidget);
    expect(find.textContaining('GPT completed'), findsOneWidget);
    expect(find.text('주말 전 강화된 C 점수 기준을 충족하지 못해 매수하지 않았습니다.'), findsOneWidget);
    expect(find.text('주문: 미제출 · 체결: 미확인'), findsOneWidget);
    expect(find.textContaining('매수 완료'), findsNothing);
    await tester
        .tap(find.byKey(const ValueKey('home-ai-execution-details-11:10')));
    await tester.pumpAndSettle();
    for (final text in [
      'C 퀀트 점수: 74.94',
      '필요한 C 점수: 75.00',
      '부족 점수: 0.06',
      '최종 매수 점수: 72.45',
      '필요한 최종 점수: 70.00',
      '최종 점수 결과: 통과'
    ]) {
      expect(find.text(text), findsOneWidget);
    }
    expect(tester.takeException(), isNull);
  });

  for (final filled in [false, true]) {
    testWidgets(
        'B: submitted BUY only confirms fill with explicit evidence: $filled',
        (tester) async {
      final slot = esoneSlot()
        ..['status'] = 'result'
        ..['scheduler_status'] = 'completed'
        ..['execution_status'] = 'submitted'
        ..['execution_reason'] = 'order_submitted'
        ..['broker_submit_called'] = true
        ..['real_order_submitted'] = true
        ..['order_status'] = filled ? 'FILLED' : 'BROKER SUBMITTED'
        ..['fill_status'] = filled ? 'FILLED' : 'SUBMITTED';
      await showFeed(tester, feed([slot]));
      expect(find.text('실제 매수: ${filled ? '체결 확인' : '매수 제출'}'), findsOneWidget);
      expect(
          find.text('주문: 제출 · 체결: ${filled ? '확인' : '미확인'}'), findsOneWidget);
      expect(find.textContaining('주말 전 강화된'), findsNothing);
    });
  }

  testWidgets('C: no completed candidate is HOLD without old block messages',
      (tester) async {
    await showFeed(
        tester,
        feed([
          {
            'scheduler_slot': '12:20',
            'status': 'analysis_complete',
            'scheduler_status': 'blocked',
            'execution_reason': 'no_gpt_completed_execution_candidate',
            'reason': 'no_gpt_completed_execution_candidate',
            'final_failure_reason': reason,
            'ai_reason': '과거 차단 문구',
          }
        ]));
    expect(find.text('AI 분석: HOLD'), findsOneWidget);
    expect(find.text('실제 매수: HOLD'), findsOneWidget);
    expect(find.text('AI 분석 완료 후보 없음'), findsOneWidget);
    expect(find.textContaining('주말 전'), findsNothing);
    expect(find.textContaining('과거 차단'), findsNothing);
  });

  testWidgets('canonical normal HOLD stays separate from completed analysis',
      (tester) async {
    await showFeed(
        tester,
        feed([
          {
            'scheduler_slot': '12:20',
            'status': 'analysis_complete',
            'scheduler_status': 'HOLD',
            'execution_status': 'hold',
            'execution_reason': 'weak_signal',
            'action': 'hold',
          }
        ]));
    expect(find.text('AI 분석: 완료'), findsOneWidget);
    expect(find.text('실제 매수: HOLD'), findsOneWidget);
  });

  for (final missing in ['score', 'threshold', 'both']) {
    testWidgets('D: missing $missing never invents a score or shortfall',
        (tester) async {
      final slot = esoneSlot();
      if (missing != 'threshold') {
        slot['calendar_gap_candidate_diagnostics'] = [];
      }
      if (missing != 'score') {
        slot['calendar_gap_risk'] = {};
      }
      await showFeed(tester, feed([slot]));
      await tester
          .tap(find.byKey(const ValueKey('home-ai-execution-details-11:10')));
      await tester.pumpAndSettle();
      expect(find.textContaining('확인 불가'), findsWidgets);
      expect(find.textContaining('부족 점수:'), findsNothing);
      expect(find.text('필요한 C 점수: 65.00'), findsNothing);
      expect(find.text('C 퀀트 점수: 62.00'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  test(
      'E: feed rejects explicit owner/profile/date mismatches without merging slots',
      () {
    final current = feed([
      esoneSlot(),
      {...esoneSlot(), 'owner_user_id': 2},
      {...esoneSlot(), 'profile_id': 8},
      {...esoneSlot(), 'trade_date_kst': '2026-11-12'},
      {'scheduler_slot': '12:20', 'status': 'analysis_pending'},
    ]);
    expect(current.slots, hasLength(2));
    expect(current.slots.last.quantCScore, isNull);
    expect(current.slots.last.executionReasonCode, isNull);
  });

  test('E: refresh and account switch reject late previous results', () async {
    final oldResponse = Completer<AutomationTodayDecisions>();
    final newResponse = Completer<AutomationTodayDecisions>();
    final api = _FeedApi()..pending.addAll([oldResponse, newResponse]);
    final admin = DashboardController(api, autoload: false);
    admin.beginAuthenticatedSession(const AuthUser(
        id: 1,
        username: 'admin',
        role: 'admin',
        enabled: true,
        setupCompleted: true));
    addTearDown(admin.dispose);
    final oldRequest = admin.refreshTodayAiDecisions();
    final newRequest = admin.refreshTodayAiDecisions();
    expect(admin.todayAiDecisions.slots, isEmpty);
    newResponse.complete(feed([
      {
        'scheduler_slot': '12:20',
        'status': 'analysis_complete',
        'reason': 'no_gpt_completed_execution_candidate'
      }
    ], day: '2026-11-16'));
    await newRequest;
    oldResponse.complete(feed([esoneSlot()]));
    await oldRequest;
    expect(admin.todayAiDecisions.slots.single.schedulerSlot, '12:20');
    expect(admin.todayAiDecisions.tradeDateKst, '2026-11-16');
    final user = admin.beginAuthenticatedSession(const AuthUser(
        id: 2,
        username: 'test01',
        role: 'user',
        enabled: true,
        setupCompleted: true));
    addTearDown(user.dispose);
    expect(user.todayAiDecisions.slots, isEmpty);
    await user.refreshTodayAiDecisions(userScoped: true);
    expect(user.todayAiDecisions.ownerUserId, 2);
    expect(user.todayAiDecisions.slots.single.executionReasonCode,
        'no_gpt_completed_execution_candidate');
    expect(user.todayAiDecisions.slots.single.quantCScore, isNull);
  });

  test('stale scheduler reason does not override a newer analysis', () {
    final slot = esoneSlot()
      ..['scheduler_outcome_applied'] = false
      ..['reason'] = 'no_gpt_completed_execution_candidate';
    expect(AutomationTodayDecisionSlot.fromJson(slot).executionReasonCode,
        'no_gpt_completed_execution_candidate');
  });
}

class _FeedApi extends ApiClient {
  final pending = <Completer<AutomationTodayDecisions>>[];
  @override
  Future<AutomationTodayDecisions> fetchAdminTodayAiDecisions() =>
      pending.removeAt(0).future;
  @override
  Future<AutomationTodayDecisions> fetchUserTodayAiDecisions() async => feed([
        {
          'scheduler_slot': '12:20',
          'status': 'analysis_complete',
          'reason': 'no_gpt_completed_execution_candidate'
        }
      ], owner: 2, profile: 8);
}
