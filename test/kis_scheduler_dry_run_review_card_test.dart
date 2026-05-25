import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_dry_run_review.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('fetchKisSchedulerDryRunReview calls review endpoint only', () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_reviewJson()), 200);
      }),
    );

    final result = await client.fetchKisSchedulerDryRunReview(
      limit: 7,
      days: 14,
      includeRaw: true,
      slotLabel: 'manual_dry_run',
      module: 'limited_auto_buy',
    );

    expect(captured.method, 'GET');
    expect(captured.url.path, '/kis/scheduler/dry-run-review');
    expect(captured.url.queryParameters['limit'], '7');
    expect(captured.url.queryParameters['days'], '14');
    expect(captured.url.queryParameters['include_raw'], 'true');
    expect(captured.url.queryParameters['slot_label'], 'manual_dry_run');
    expect(captured.url.queryParameters['module'], 'limited_auto_buy');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(
        captured.url.path, isNot(contains('/kis/limited-auto-buy/run-once')));
    expect(result.mode, 'kis_scheduler_dry_run_review');
    expect(result.brokerSubmitCalled, isFalse);
  });

  testWidgets('scheduler dry-run review card renders empty safe state',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeSchedulerDryRunReviewApi());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_dry_run_review_card'));
    expect(card, findsOneWidget);
    for (final label in [
      'SCHEDULER DRY-RUN REVIEW',
      'OPERATOR AUDIT',
      'REVIEW ONLY',
      'NO BROKER SUBMIT',
      'REAL ORDERS DISABLED',
      'SAFETY INVARIANTS',
      'SELL BEFORE BUY',
    ]) {
      expect(
          find.descendant(of: card, matching: find.text(label)), findsWidgets);
    }
    expect(
      find.descendant(
        of: card,
        matching: find.text(
            'No scheduler dry-run review data yet. Safety review remains read-only.'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('refresh dry-run review displays summary and no-submit flags',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeSchedulerDryRunReviewApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_dry_run_review_card'));
    final button = find.descendant(
      of: card,
      matching: find.text('Refresh Dry-run Review'),
    );
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(api.reviewCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.descendant(of: card, matching: find.text('2')), findsWidgets);
    expect(find.descendant(of: card, matching: find.text('1 / 0 / 1')),
        findsOneWidget);
    expect(
        find.descendant(of: card, matching: find.text('review_buy_candidate')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('Broker submit: No')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('Manual submit: No')),
        findsWidgets);
    expect(
        find.descendant(
            of: card, matching: find.text('Real order submitted: No')),
        findsWidgets);

    controller.dispose();
  });

  testWidgets('review card renders child modules sell before buy',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeSchedulerDryRunReviewApi())
      ..latestKisSchedulerDryRunReview =
          KisSchedulerDryRunReview.fromJson(_reviewJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_dry_run_review_card'));
    final sell = find.descendant(
      of: card,
      matching: find.text('limited_auto_sell'),
    );
    final buy = find.descendant(
      of: card,
      matching: find.text('limited_auto_buy'),
    );
    expect(sell, findsOneWidget);
    expect(buy, findsOneWidget);
    expect(tester.getTopLeft(sell).dy < tester.getTopLeft(buy).dy, isTrue);

    controller.dispose();
  });

  testWidgets('review card renders top block reasons and safety violations',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeSchedulerDryRunReviewApi())
      ..latestKisSchedulerDryRunReview =
          KisSchedulerDryRunReview.fromJson(_reviewJson(violation: true));

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_dry_run_review_card'));
    expect(
        find.descendant(
            of: card, matching: find.text('Scheduler Real Orders Disabled: 2')),
        findsOneWidget);
    expect(
        find.descendant(
            of: card, matching: find.text('Broker Submit Called True')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('SAFETY VIOLATION')),
        findsOneWidget);

    controller.dispose();
  });

  testWidgets('review card renders no-violation state and keeps raw collapsed',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeSchedulerDryRunReviewApi())
      ..latestKisSchedulerDryRunReview =
          KisSchedulerDryRunReview.fromJson(_reviewJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_dry_run_review_card'));
    expect(
      find.descendant(
        of: card,
        matching: find.text('No scheduler dry-run safety violations detected'),
      ),
      findsOneWidget,
    );
    expect(
        find.descendant(of: card, matching: find.text('Developer Raw Payload')),
        findsOneWidget);
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining('"provider": "kis"'),
      ),
      findsNothing,
    );

    controller.dispose();
  });
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 9000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

DashboardController _controller(_FakeSchedulerDryRunReviewApi api) {
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

class _FakeSchedulerDryRunReviewApi extends ApiClient {
  int reviewCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisSchedulerDryRunReview> fetchKisSchedulerDryRunReview({
    int limit = 20,
    int days = 30,
    bool includeRaw = false,
    String? slotLabel,
    String? module,
  }) async {
    reviewCalls += 1;
    return KisSchedulerDryRunReview.fromJson(_reviewJson());
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

Map<String, dynamic> _reviewJson({bool violation = false}) {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_scheduler_dry_run_review',
    'review_only': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'order_log_created': false,
    'summary': {
      'total_runs': 2,
      'completed_count': 1,
      'blocked_count': 0,
      'partial_count': 1,
      'sell_candidates_reviewed': 2,
      'buy_candidates_reviewed': 1,
      'sell_ready_count': 1,
      'buy_ready_count': 1,
      'buy_skipped_after_sell_review_count': 1,
      'submitted_order_count': 0,
      'broker_submit_count': 0,
      'manual_submit_count': 0,
      'order_log_created_count': 0,
      'no_submit_invariant_ok': !violation,
      'sell_before_buy_ordering_ok': true,
      'latest_run_at': '2026-05-24T09:10:00',
      'latest_slot_label': 'manual_dry_run',
      'latest_result': 'completed',
      'latest_primary_block_reason': 'scheduler_real_orders_disabled',
      'latest_recommended_operator_action': 'review_buy_candidate',
    },
    'recent_runs': [
      {
        'run_id': 1,
        'created_at': '2026-05-24T09:10:00',
        'slot_label': 'manual_dry_run',
        'trigger_source': 'scheduler_dry_run_orchestration',
        'mode': 'kis_scheduler_dry_run_orchestration',
        'result': 'completed',
        'primary_block_reason': 'scheduler_real_orders_disabled',
        'block_reasons': ['scheduler_real_orders_disabled'],
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
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'child_runs': [
          _child('limited_auto_sell', 'blocked', 'hold', '005930',
              'no_held_position', 0),
          _child('limited_auto_buy', 'ready', 'buy_ready', '035420',
              'dry_run_enabled', 1),
        ],
      },
    ],
    'top_block_reasons': [
      {
        'reason': 'scheduler_real_orders_disabled',
        'label': 'Scheduler Real Orders Disabled',
        'count': 2,
      },
    ],
    'module_summary': {
      'scheduler_readiness': {
        'run_count': 1,
        'blocked_count': 1,
      },
      'limited_auto_sell': {
        'run_count': 1,
        'sell_ready_count': 1,
        'blocked_count': 1,
        'top_block_reason': 'no_held_position',
      },
      'limited_auto_buy': {
        'run_count': 1,
        'buy_ready_count': 1,
        'blocked_count': 1,
        'skipped_after_sell_review_count': 1,
        'top_block_reason': 'dry_run_enabled',
      },
      'portfolio_management': {
        'run_count': 1,
        'reviewed_count': 1,
      },
    },
    'safety_violations': violation
        ? [
            {
              'reason': 'broker_submit_called_true',
              'label': 'Broker Submit Called True',
              'run_id': 1,
              'module': null,
            },
          ]
        : [],
    'latest_recommended_operator_action': 'review_buy_candidate',
    'safety': {
      'review_only': true,
      'no_broker_submit_from_review': true,
      'scheduler_real_orders_enabled': false,
      'kis_scheduler_allow_real_orders': false,
      'no_submit_invariant_ok': !violation,
      'sell_before_buy_ordering_ok': true,
      'existing_scheduler_dry_run_unchanged': true,
      'existing_guarded_buy_sell_unchanged': true,
    },
    'diagnostics': {
      'source_row_count': 2,
      'ignored_row_count': 0,
      'malformed_row_count': 0,
      'include_raw': false,
      'filters_applied': {'limit': 20, 'days': 30},
      'price_forward_metrics_available': false,
    },
  };
}

Map<String, dynamic> _child(
  String module,
  String result,
  String action,
  String symbol,
  String primaryBlockReason,
  int readyCount,
) {
  return {
    'module': module,
    'result': result,
    'action': action,
    'symbol': symbol,
    'status': 'ok',
    'primary_block_reason': primaryBlockReason,
    'block_reasons': [primaryBlockReason],
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'order_id': null,
    'mode': module,
    'source': module,
    'trigger_source': 'scheduler_dry_run_orchestration',
    'summary': {
      'candidates_reviewed': 1,
      'ready_count': readyCount,
    },
  };
}
