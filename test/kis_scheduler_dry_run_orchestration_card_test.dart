import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_dry_run_orchestration.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('runKisSchedulerDryRunOrchestrationOnce posts scheduler endpoint only',
      () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_orchestrationJson()), 200);
      }),
    );

    final result = await client.runKisSchedulerDryRunOrchestrationOnce();

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/scheduler/run-dry-run-orchestration-once');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(
        captured.url.path, isNot(contains('/kis/limited-auto-buy/run-once')));
    expect(
        captured.url.path, isNot(contains('/kis/limited-auto-sell/run-once')));
    expect(result.mode, 'kis_scheduler_dry_run_orchestration');
    expect(result.realOrderSubmitted, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
  });

  testWidgets('scheduler dry-run card renders safe labels and child modules',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 7000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerDryRunApi();
    final controller = _controller(api)
      ..latestKisSchedulerDryRunOrchestration =
          KisSchedulerDryRunOrchestration.fromJson(_orchestrationJson());

    await tester.pumpWidget(_wrap(controller));

    final card =
        find.byKey(const Key('kis_scheduler_dry_run_orchestration_card'));
    expect(card, findsOneWidget);
    for (final label in [
      'SCHEDULER DRY-RUN',
      'ORCHESTRATION',
      'READINESS ONLY',
      'REAL ORDERS DISABLED',
      'NO BROKER SUBMIT',
      'POSITION MANAGEMENT FIRST',
      'BUY AFTER SELL REVIEW',
    ]) {
      expect(
          find.descendant(of: card, matching: find.text(label)), findsWidgets);
    }
    expect(find.descendant(of: card, matching: find.text('completed')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('manual_dry_run')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('limited_auto_sell')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('limited_auto_buy')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('Broker submit: No')),
        findsWidgets);
    expect(
        find.descendant(
            of: card, matching: find.text('Real order submitted: No')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('Manual submit: No')),
        findsWidgets);
    expect(
        find.descendant(of: card, matching: find.text('Developer Raw Payload')),
        findsOneWidget);
    expect(
        find.descendant(
            of: card, matching: find.textContaining('"provider": "kis"')),
        findsNothing);

    controller.dispose();
  });

  testWidgets('run scheduler dry-run once displays parent summary',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 7000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerDryRunApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    final card =
        find.byKey(const Key('kis_scheduler_dry_run_orchestration_card'));
    final button = find.descendant(
      of: card,
      matching: find.text('Run Scheduler Dry-run Once'),
    );
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(api.calls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.descendant(of: card, matching: find.text('completed')),
        findsWidgets);
    expect(
        find.descendant(of: card, matching: find.text('review_buy_candidate')),
        findsOneWidget);

    controller.dispose();
  });
}

DashboardController _controller(_FakeSchedulerDryRunApi api) {
  return DashboardController(api, autoload: false)
    ..selectedProvider = SelectedProvider.kis
    ..krWatchlist = MarketWatchlist.empty('KR');
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => TestLabSection(
              controller: controller, advancedInitiallyExpanded: true),
        ),
      ),
    ),
  );
}

class _FakeSchedulerDryRunApi extends ApiClient {
  int calls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisSchedulerDryRunOrchestration>
      runKisSchedulerDryRunOrchestrationOnce({
    String? slotLabel,
    bool includeBuy = true,
    bool includeSell = true,
    bool includeRaw = false,
  }) async {
    calls += 1;
    return KisSchedulerDryRunOrchestration.fromJson(_orchestrationJson());
  }

  @override
  Future<List<TradingRun>> getRecentTradingRuns() async => const [];

  @override
  Future<OrderValidationResult> validateKisOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    Map<String, dynamic>? sourceMetadata,
  }) async {
    validationCalls += 1;
    throw const ApiRequestException('validation should not run');
  }

  @override
  Future<KisManualOrderResult> submitKisManualOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    required bool confirmLive,
    Map<String, dynamic>? sourceMetadata,
  }) async {
    submitCalls += 1;
    throw const ApiRequestException('submit should not run');
  }
}

Map<String, dynamic> _orchestrationJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_scheduler_dry_run_orchestration',
    'trigger_source': 'scheduler_dry_run_orchestration',
    'slot_label': 'manual_dry_run',
    'result': 'completed',
    'readiness_only': true,
    'dry_run': true,
    'scheduler_real_orders_enabled': false,
    'real_order_submit_allowed': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'parent_run_id': 1,
    'parent_run_key': 'kis_scheduler_dry_run_test',
    'summary': {
      'modules_requested': [
        'scheduler_readiness',
        'portfolio_management',
        'limited_auto_sell',
        'limited_auto_buy',
      ],
      'modules_completed': [
        'scheduler_readiness',
        'portfolio_management',
        'limited_auto_sell',
        'limited_auto_buy',
      ],
      'modules_blocked': ['scheduler_readiness'],
      'sell_candidates_reviewed': 1,
      'buy_candidates_reviewed': 1,
      'sell_ready_count': 0,
      'buy_ready_count': 1,
      'submitted_order_count': 0,
      'broker_submit_count': 0,
      'manual_submit_count': 0,
      'real_order_submit_allowed': false,
      'primary_block_reason': 'scheduler_real_orders_disabled',
      'top_block_reasons': ['scheduler_real_orders_disabled'],
      'next_recommended_operator_action': 'review_buy_candidate',
    },
    'child_runs': [
      {
        'module': 'limited_auto_sell',
        'result': 'blocked',
        'action': 'hold',
        'symbol': '005930',
        'status': 'ok',
        'primary_block_reason': 'no_held_position',
        'block_reasons': ['no_held_position'],
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'order_id': null,
        'source': 'kis_limited_auto_stop_loss',
        'mode': 'kis_limited_auto_stop_loss_preflight',
        'trigger_source': 'kis_limited_auto_sell',
        'summary': {
          'candidates_reviewed': 1,
          'ready_count': 0,
        },
      },
      {
        'module': 'limited_auto_buy',
        'result': 'ready',
        'action': 'buy_ready',
        'symbol': '035420',
        'status': 'ok',
        'primary_block_reason': 'dry_run_enabled',
        'block_reasons': ['dry_run_enabled'],
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'order_id': null,
        'source': 'kis_limited_auto_buy',
        'mode': 'kis_limited_auto_buy_preflight',
        'trigger_source': 'limited_auto_buy_preflight',
        'summary': {
          'candidates_reviewed': 1,
          'ready_count': 1,
        },
      },
    ],
    'block_reasons': ['scheduler_real_orders_disabled'],
    'safety': {
      'scheduler_dry_run_orchestration': true,
      'readiness_only': true,
      'no_broker_submit': true,
      'no_manual_submit': true,
      'no_order_log_created': true,
      'scheduler_real_orders_enabled': false,
      'kis_scheduler_allow_real_orders': false,
      'existing_buy_execution_unchanged': true,
      'existing_sell_execution_unchanged': true,
      'limited_buy_called_in_dry_run_mode': true,
      'limited_sell_called_in_dry_run_mode': true,
    },
    'diagnostics': {},
  };
}
