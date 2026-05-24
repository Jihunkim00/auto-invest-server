import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_sell_review.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';

void main() {
  test('fetchKisSchedulerGuardedSellReview calls review endpoint only',
      () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_reviewJson()), 200);
      }),
    );

    final result = await client.fetchKisSchedulerGuardedSellReview(
      limit: 7,
      days: 14,
      symbol: '005930',
      includeRaw: true,
      result: 'submitted',
    );

    expect(captured.method, 'GET');
    expect(captured.url.path, '/kis/scheduler/guarded-sell/review');
    expect(captured.url.queryParameters['limit'], '7');
    expect(captured.url.queryParameters['days'], '14');
    expect(captured.url.queryParameters['symbol'], '005930');
    expect(captured.url.queryParameters['include_raw'], 'true');
    expect(captured.url.queryParameters['result'], 'submitted');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/validate')));
    expect(result.reviewOnly, isTrue);
    expect(result.buyExecutionAllowed, isFalse);
  });

  testWidgets('guarded sell review card renders empty state', (tester) async {
    await _setLargeView(tester);
    final controller = _controller(
      _FakeGuardedSellReviewApi(
        review: KisSchedulerGuardedSellReview.fromJson(_emptyReviewJson()),
      ),
    );

    await tester.pumpWidget(_wrap(controller));

    final card =
        find.byKey(const Key('kis_scheduler_guarded_sell_review_card'));
    expect(card, findsOneWidget);
    for (final label in [
      'SCHEDULER GUARDED SELL REVIEW',
      'OPERATOR AUDIT',
      'SELL ONLY',
      'BUY DISABLED',
      'REVIEW ONLY',
      'NO BROKER SUBMIT',
      'SAFETY INVARIANTS',
    ]) {
      expect(
          find.descendant(of: card, matching: find.text(label)), findsWidgets);
    }

    final button = find.descendant(
      of: card,
      matching: find.text('Refresh Guarded Sell Review'),
    );
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(find.descendant(of: card, matching: find.text('total attempts')),
        findsNothing);
    expect(
      find.descendant(
        of: card,
        matching: find.text('No scheduler guarded sell attempts recorded.'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: card,
        matching:
            find.text('No scheduler guarded sell safety violations detected'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets(
      'guarded sell review summary renders submitted and blocked counts',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeGuardedSellReviewApi())
      ..latestKisSchedulerGuardedSellReview =
          KisSchedulerGuardedSellReview.fromJson(_reviewJson());

    await tester.pumpWidget(_wrap(controller));

    final card =
        find.byKey(const Key('kis_scheduler_guarded_sell_review_card'));
    expect(find.descendant(of: card, matching: find.text('2')), findsWidgets);
    expect(
      find.descendant(
        of: card,
        matching:
            find.text('No scheduler guarded sell safety violations detected'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: card,
        matching: find.text('Scheduler Real Orders Disabled: 1'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('guarded sell review submitted item renders order id and ODNO',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeGuardedSellReviewApi())
      ..latestKisSchedulerGuardedSellReview =
          KisSchedulerGuardedSellReview.fromJson(_reviewJson());

    await tester.pumpWidget(_wrap(controller));

    final card =
        find.byKey(const Key('kis_scheduler_guarded_sell_review_card'));
    expect(find.descendant(of: card, matching: find.text('005930 · Samsung')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('321')), findsWidgets);
    expect(find.descendant(of: card, matching: find.text('KIS-321')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('Broker submit: Yes')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('Manual submit: Yes')),
        findsWidgets);

    controller.dispose();
  });

  testWidgets('guarded sell review blocked item renders no submit labels',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeGuardedSellReviewApi())
      ..latestKisSchedulerGuardedSellReview =
          KisSchedulerGuardedSellReview.fromJson(_reviewJson());

    await tester.pumpWidget(_wrap(controller));

    final card =
        find.byKey(const Key('kis_scheduler_guarded_sell_review_card'));
    expect(
        find.descendant(of: card, matching: find.text('035420')), findsWidgets);
    expect(
      find.descendant(
        of: card,
        matching: find.text('scheduler_real_orders_disabled'),
      ),
      findsWidgets,
    );
    expect(find.descendant(of: card, matching: find.text('Broker submit: No')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('Manual submit: No')),
        findsWidgets);
    expect(
      find.descendant(
        of: card,
        matching: find.text('Real order submitted: No'),
      ),
      findsWidgets,
    );

    controller.dispose();
  });

  testWidgets('guarded sell review safety violation renders warning',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeGuardedSellReviewApi())
      ..latestKisSchedulerGuardedSellReview =
          KisSchedulerGuardedSellReview.fromJson(_reviewJson(violation: true));

    await tester.pumpWidget(_wrap(controller));

    final card =
        find.byKey(const Key('kis_scheduler_guarded_sell_review_card'));
    expect(find.descendant(of: card, matching: find.text('SAFETY VIOLATION')),
        findsOneWidget);
    expect(
      find.descendant(
        of: card,
        matching: find.text('Scheduler Guarded Sell Buy Execution Allowed'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('guarded sell review raw payload is collapsed by default',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeGuardedSellReviewApi())
      ..latestKisSchedulerGuardedSellReview =
          KisSchedulerGuardedSellReview.fromJson(_reviewJson());

    await tester.pumpWidget(_wrap(controller));

    final card =
        find.byKey(const Key('kis_scheduler_guarded_sell_review_card'));
    expect(
      find.descendant(of: card, matching: find.text('Developer Raw Payload')),
      findsOneWidget,
    );
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
  tester.view.physicalSize = const Size(1200, 9800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

DashboardController _controller(_FakeGuardedSellReviewApi api) {
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
          builder: (context, _) => TestLabSection(controller: controller),
        ),
      ),
    ),
  );
}

class _FakeGuardedSellReviewApi extends ApiClient {
  _FakeGuardedSellReviewApi({KisSchedulerGuardedSellReview? review})
      : review =
            review ?? KisSchedulerGuardedSellReview.fromJson(_reviewJson());

  KisSchedulerGuardedSellReview review;
  int reviewCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisSchedulerGuardedSellReview> fetchKisSchedulerGuardedSellReview({
    int limit = 20,
    int days = 30,
    String? symbol,
    bool includeRaw = false,
    String? result,
  }) async {
    reviewCalls += 1;
    return review;
  }

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

Map<String, dynamic> _emptyReviewJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_scheduler_guarded_sell_review',
    'review_only': true,
    'sell_only': true,
    'buy_execution_allowed': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'order_log_created': false,
    'summary': {
      'total_attempts': 0,
      'submitted_count': 0,
      'blocked_count': 0,
      'failed_count': 0,
      'skipped_count': 0,
      'stop_loss_submit_count': 0,
      'take_profit_submit_count': 0,
      'duplicate_order_block_count': 0,
      'daily_limit_block_count': 0,
      'dry_run_block_count': 0,
      'kill_switch_block_count': 0,
      'scheduler_disabled_block_count': 0,
      'scheduler_sell_disabled_block_count': 0,
      'scheduler_real_orders_disabled_block_count': 0,
      'kis_real_order_disabled_block_count': 0,
      'validation_failed_count': 0,
      'no_candidate_count': 0,
      'sell_only_invariant_ok': true,
      'no_direct_scheduler_submit_invariant_ok': true,
      'buy_execution_never_called': true,
      'submitted_rows_have_order_ids': true,
      'submitted_rows_have_kis_odno_count': 0,
      'submitted_rows_have_audit_metadata': true,
      'max_daily_sell_count_observed': 0,
    },
    'recent_attempts': [],
    'submitted_sells': [],
    'blocked_attempts': [],
    'top_block_reasons': [],
    'daily_usage': [],
    'safety_violations': [],
    'safety': {
      'review_only': true,
      'sell_only': true,
      'buy_execution_allowed': false,
    },
    'diagnostics': {'include_raw': false},
  };
}

Map<String, dynamic> _reviewJson({bool violation = false}) {
  return {
    ..._emptyReviewJson(),
    'summary': {
      ...(_emptyReviewJson()['summary'] as Map<String, dynamic>),
      'total_attempts': 2,
      'submitted_count': 1,
      'blocked_count': 1,
      'stop_loss_submit_count': 1,
      'scheduler_real_orders_disabled_block_count': 1,
      'submitted_rows_have_kis_odno_count': 1,
      'max_daily_sell_count_observed': 1,
      'latest_attempt_at': '2026-05-25T00:20:00Z',
      'latest_submitted_at': '2026-05-25T00:20:00Z',
      'latest_blocked_at': '2026-05-25T00:10:00Z',
      'latest_symbol': '005930',
      'latest_result': 'submitted',
      'sell_only_invariant_ok': !violation,
    },
    'recent_attempts': [
      {
        'run_id': 2,
        'created_at': '2026-05-25T00:20:00Z',
        'slot_label': 'position_management',
        'trigger_source': 'scheduler_guarded_sell',
        'mode': 'kis_scheduler_guarded_sell',
        'result': 'submitted',
        'action': 'sell',
        'symbol': '005930',
        'company_name': 'Samsung',
        'primary_block_reason': null,
        'block_reasons': [],
        'sell_only': true,
        'buy_execution_allowed': false,
        'scheduler_real_orders_enabled': true,
        'kis_scheduler_sell_enabled': true,
        'dry_run': false,
        'kill_switch': false,
        'kis_real_order_enabled': true,
        'kis_live_auto_sell_enabled': true,
        'stop_loss_enabled': true,
        'take_profit_enabled': false,
        'real_order_submitted': true,
        'broker_submit_called': true,
        'manual_submit_called': true,
        'order_id': 321,
        'kis_odno': 'KIS-321',
        'trigger': 'stop_loss',
        'child_sell_result': {'trigger': 'stop_loss'},
      },
      {
        'run_id': 1,
        'created_at': '2026-05-25T00:10:00Z',
        'slot_label': 'position_management',
        'trigger_source': 'scheduler_guarded_sell',
        'mode': 'kis_scheduler_guarded_sell',
        'result': 'blocked',
        'action': 'hold',
        'symbol': '035420',
        'primary_block_reason': 'scheduler_real_orders_disabled',
        'block_reasons': ['scheduler_real_orders_disabled'],
        'sell_only': true,
        'buy_execution_allowed': false,
        'scheduler_real_orders_enabled': false,
        'kis_scheduler_sell_enabled': false,
        'dry_run': true,
        'kill_switch': false,
        'kis_real_order_enabled': false,
        'kis_live_auto_sell_enabled': false,
        'stop_loss_enabled': false,
        'take_profit_enabled': false,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'order_id': null,
        'kis_odno': null,
        'child_sell_result': {},
      },
    ],
    'submitted_sells': [
      {
        'order_id': 321,
        'broker_order_id': 'BRK-321',
        'kis_odno': 'KIS-321',
        'created_at': '2026-05-25T00:20:00Z',
        'symbol': '005930',
        'company_name': 'Samsung',
        'side': 'sell',
        'quantity': 3,
        'current_price': 70000,
        'estimated_notional': 210000,
        'trigger': 'stop_loss',
        'source': 'kis_limited_auto_stop_loss',
        'source_type': 'guarded_stop_loss_auto_sell',
        'mode': 'kis_limited_auto_stop_loss_run',
        'trigger_source': 'kis_limited_auto_sell',
        'parent_scheduler_run_id': 2,
        'real_order_submitted': true,
        'broker_submit_called': true,
        'manual_submit_called': true,
        'internal_status': 'SUBMITTED',
      },
    ],
    'blocked_attempts': [
      {
        'run_id': 1,
        'created_at': '2026-05-25T00:10:00Z',
        'symbol': '035420',
        'result': 'blocked',
        'action': 'hold',
        'primary_block_reason': 'scheduler_real_orders_disabled',
        'block_reasons': ['scheduler_real_orders_disabled'],
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      },
    ],
    'top_block_reasons': [
      {
        'reason': 'scheduler_real_orders_disabled',
        'label': 'Scheduler Real Orders Disabled',
        'count': 1,
      },
    ],
    'daily_usage': [
      {
        'date': '2026-05-25',
        'submitted_sell_count': 1,
        'symbols': ['005930'],
        'triggers': ['stop_loss'],
        'total_estimated_notional': 210000,
        'daily_limit': 1,
        'limit_exceeded': false,
      },
    ],
    'safety_violations': violation
        ? [
            {
              'reason': 'scheduler_guarded_sell_buy_execution_allowed',
              'label': 'Scheduler Guarded Sell Buy Execution Allowed',
              'run_id': 9,
              'symbol': '005930',
            },
          ]
        : [],
  };
}
