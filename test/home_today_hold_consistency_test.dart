import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/home_latest_ai_decision_card.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/automation_today_decisions.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';

const noCandidate = 'no_gpt_completed_execution_candidate';
const holdText = '매수 조건을 충족한 AI 분석 완료 후보가 없어 HOLD했습니다.';
const wrongPositionText = '포지션 또는 청산 확인이 완료되지 않아 매수를 차단했습니다.';

AutomationTodayDecisions feed(String reason,
        {String status = 'blocked', int owner = 1}) =>
    AutomationTodayDecisions.fromJson({
      'trade_date_kst': '2026-11-10',
      'profile_id': owner == 1 ? 5 : 8,
      'profile_key': owner == 1 ? 'admin-kis' : 'test01',
      'owner_user_id': owner,
      'slots': [
        {
          'scheduler_slot': '13:30',
          'status': status,
          'reason': reason,
          'action': 'hold',
          'created_at': '2026-11-10T04:31:45Z',
        }
      ],
    });

Future<void> show(WidgetTester tester, DashboardController controller) =>
    tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
      child: HomeLatestAiDecisionCard(controller: controller),
    ))));

void main() {
  test('admin and regular-user HTTP requests use separate uncached endpoints',
      () async {
    final requests = <http.Request>[];
    final payload = File('test/fixtures/admin_today_decisions_20261110.json')
        .readAsStringSync();
    final client = ApiClient(client: MockClient((request) async {
      requests.add(request);
      return http.Response(payload, 200,
          headers: {'content-type': 'application/json'});
    }));
    await client.fetchAdminTodayAiDecisions();
    await client.fetchUserTodayAiDecisions();
    expect(requests.map((request) => request.url.path).toList(), [
      '/runs/automation/ai-decisions/today',
      '/users/me/trading/ai-decisions/today',
    ]);
    for (final request in requests) {
      expect(request.method, 'GET');
      expect(request.headers['Cache-Control'], 'no-cache');
      expect(request.url.queryParameters['_ts'], isNotEmpty);
    }
  });
  testWidgets(
      'observed Nov10 API blocked ledger displays HOLD for all three slots',
      (tester) async {
    final observed = jsonDecode(
        File('test/fixtures/admin_today_decisions_20261110.json')
            .readAsStringSync());
    final controller = DashboardController(ApiClient(), autoload: false)
      ..todayAiDecisionsLoaded = true
      ..todayAiDecisions = AutomationTodayDecisions.fromJson(
          Map<String, dynamic>.from(observed));
    addTearDown(controller.dispose);
    await show(tester, controller);
    expect(find.text(holdText), findsNWidgets(3));
    expect(find.text(wrongPositionText), findsNothing);
    expect(find.text('매수 진입 차단'), findsNothing);
    expect(find.textContaining('13:30 · HOLD'), findsOneWidget);
    final latest = tester
        .getTopLeft(find.byKey(const ValueKey('home-ai-slot-card-13:30')))
        .dy;
    final history = tester.getTopLeft(find.text('이전 슬롯 실행 이력')).dy;
    expect(latest, lessThan(history));
  });

  test(
      'current HOLD reason takes priority over stale failure and candidate risk flags',
      () {
    final slot = AutomationTodayDecisionSlot.fromJson({
      'scheduler_slot': '13:30',
      'status': 'analysis_complete',
      'reason': noCandidate,
      'final_failure_reason': 'position_retry_exit_unresolved',
      'risk_flags': ['position_state_refresh_pending'],
      'gating_notes': ['position_retry_exit_unresolved'],
      'analysis_candidates': [
        {
          'symbol': '005930',
          'gpt_analysis_status': 'completed',
          'block_reason': 'position_retry_exit_unresolved',
        }
      ],
    });
    expect(slot.reason, noCandidate);
    expect(slot.executionReasonCode, noCandidate);
    expect(slot.executionReasonLabel(english: false), holdText);
  });

  for (final entry in {
    'no_remaining_analysis_slot': '오늘 예정된 자동매매 분석이 모두 종료됐습니다.',
    'position_state_refresh_pending': '계좌 포지션 확인이 진행 중이어서 신규 매수를 보류했습니다.',
    'position_retry_exit_unresolved': '청산 상태 확인이 완료되지 않아 신규 매수를 차단했습니다.',
    'scheduler_task_timeout': '자동매매 분석 작업이 제한 시간 내 완료되지 않았습니다.',
  }.entries) {
    testWidgets('exact explanation for ${entry.key} with execution time',
        (tester) async {
      final controller = DashboardController(ApiClient(), autoload: false)
        ..todayAiDecisionsLoaded = true
        ..todayAiDecisions = feed(entry.key,
            status:
                entry.key == 'scheduler_task_timeout' ? 'failed' : 'blocked');
      addTearDown(controller.dispose);
      await show(tester, controller);
      expect(find.text(entry.value), findsOneWidget);
      expect(find.textContaining('2026-11-10 13:31 KST'), findsOneWidget);
      expect(find.text(wrongPositionText), findsNothing);
      if (entry.key == 'no_remaining_analysis_slot') {
        expect(find.textContaining('13:30 · DONE'), findsOneWidget);
        expect(find.text('매수 진입 차단'), findsNothing);
      }
    });
  }

  testWidgets('current HOLD hides the stale failure footer', (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..todayAiDecisionsLoaded = true
      ..todayAiDecisions = AutomationTodayDecisions.fromJson({
        'trade_date_kst': '2026-11-10',
        'profile_id': 5,
        'slots': [
          {
            'scheduler_slot': '13:30',
            'status': 'analysis_complete',
            'reason': noCandidate,
            'final_failure_reason': 'position_retry_exit_unresolved',
            'ai_reason': '과거 포지션 확인 실패',
          }
        ],
      });
    addTearDown(controller.dispose);
    await show(tester, controller);
    expect(find.text(holdText), findsOneWidget);
    expect(find.textContaining('position_retry_exit_unresolved'), findsNothing);
    expect(find.text('과거 포지션 확인 실패'), findsNothing);
  });

  testWidgets('unknown blocked reason does not invent a position problem',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..todayAiDecisionsLoaded = true
      ..todayAiDecisions = feed('unrecognized_execution_reason');
    addTearDown(controller.dispose);
    await show(tester, controller);
    expect(find.text('실행 결과 확인'), findsOneWidget);
    expect(find.text(wrongPositionText), findsNothing);
    expect(find.text('매수 진입 차단'), findsNothing);
  });

  test(
      'refresh clears old result and API failure never restores stale position text',
      () async {
    final pending = Completer<AutomationTodayDecisions>();
    final api = _FeedApi()..adminPending = pending;
    final controller = DashboardController(api, autoload: false)
      ..todayAiDecisions = feed('position_retry_exit_unresolved')
      ..todayAiDecisionsLoaded = true;
    addTearDown(controller.dispose);
    final request = controller.refreshTodayAiDecisions();
    expect(controller.todayAiDecisions.slots, isEmpty);
    expect(controller.todayAiDecisionsLoaded, isFalse);
    pending.completeError(StateError('fake API failure'));
    await request;
    expect(controller.todayAiDecisions.slots, isEmpty);
    expect(controller.todayAiDecisionsError, isNotNull);
    api.adminPending = null;
    await controller.refreshTodayAiDecisions();
    expect(controller.todayAiDecisions.slots.single.reason, noCandidate);
    expect(controller.todayAiDecisionsError, isNull);
  });

  test('dashboard refresh updates decision even when another endpoint fails',
      () async {
    final controller = DashboardController(_FeedApi(), autoload: false)
      ..todayAiDecisions = feed('position_retry_exit_unresolved')
      ..todayAiDecisionsLoaded = true;
    addTearDown(controller.dispose);
    await controller.load();
    expect(controller.error, isNotNull);
    expect(controller.todayAiDecisionsLoaded, isTrue);
    expect(controller.todayAiDecisions.slots.single.reason, noCandidate);
  });

  test(
      'account switch removes old message and rejects late previous-account response',
      () async {
    final pending = Completer<AutomationTodayDecisions>();
    final api = _FeedApi()..adminPending = pending;
    final previous = DashboardController(api, autoload: false);
    previous.beginAuthenticatedSession(const AuthUser(
        id: 1,
        username: 'admin',
        role: 'admin',
        enabled: true,
        setupCompleted: true));
    final request = previous.refreshTodayAiDecisions();
    final current = previous.beginAuthenticatedSession(const AuthUser(
        id: 2,
        username: 'test01',
        role: 'user',
        enabled: true,
        setupCompleted: true));
    addTearDown(previous.dispose);
    addTearDown(current.dispose);
    expect(current.todayAiDecisions.slots, isEmpty);
    await current.refreshTodayAiDecisions(userScoped: true);
    pending.complete(feed('position_retry_exit_unresolved'));
    await request;
    expect(current.todayAiDecisions.ownerUserId, 2);
    expect(current.todayAiDecisions.slots.single.reason, noCandidate);
    expect(previous.todayAiDecisions.slots, isEmpty);
  });
}

class _FeedApi extends ApiClient {
  Completer<AutomationTodayDecisions>? adminPending;
  @override
  Future<AutomationTodayDecisions> fetchAdminTodayAiDecisions() async =>
      adminPending == null ? feed(noCandidate) : await adminPending!.future;
  @override
  Future<AutomationTodayDecisions> fetchUserTodayAiDecisions() async =>
      feed(noCandidate, owner: 2);
  @override
  Future<OpsSettings> getOpsSettings() async =>
      throw StateError('unrelated fake endpoint failure');
}
