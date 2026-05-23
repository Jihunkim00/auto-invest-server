import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_limited_auto_buy_execution_review.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';

void main() {
  test('limited buy execution review API calls execution review endpoint',
      () async {
    final paths = <String>[];
    final client = ApiClient(
      client: MockClient((request) async {
        paths.add('${request.method} ${request.url.path}');
        return http.Response(jsonEncode(_executionReviewJson()), 200);
      }),
    );

    final review = await client.fetchKisLimitedAutoBuyExecutionReview();

    expect(paths, ['GET /kis/limited-auto-buy/execution-review']);
    expect(review.mode, 'kis_limited_auto_buy_execution_review');
    expect(review.reviewOnly, isTrue);
  });

  testWidgets('execution review card renders empty state', (tester) async {
    tester.view.physicalSize = const Size(1200, 6200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(_FakeExecutionReviewApi(
      review: _executionReview(empty: true),
    ));

    await tester.pumpWidget(_wrap(controller));

    final card =
        find.byKey(const Key('kis_limited_auto_buy_execution_review_card'));
    expect(card, findsOneWidget);
    for (final label in [
      'BUY EXECUTION REVIEW',
      'OPERATOR AUDIT',
      'REVIEW ONLY',
      'NO BROKER SUBMIT',
      'SCHEDULER REAL ORDERS DISABLED',
      'SAFETY INVARIANTS',
    ]) {
      expect(find.descendant(of: card, matching: find.text(label)),
          findsOneWidget);
    }
    expect(
      find.text(
        'No guarded limited buy execution audit rows found for the selected window.',
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('execution review summary renders submitted and blocked counts',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 7200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeExecutionReviewApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    await _refreshExecutionReview(tester);

    final card =
        find.byKey(const Key('kis_limited_auto_buy_execution_review_card'));
    expect(api.reviewCalls, 1);
    expect(
        find.descendant(of: card, matching: find.text('SUBMITTED BUY COUNT')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('BLOCKED COUNT')),
        findsOneWidget);
    expect(
        find.descendant(of: card, matching: find.text('READINESS-ONLY COUNT')),
        findsOneWidget);
    expect(find.text('No safety violations detected'), findsOneWidget);

    controller.dispose();
  });

  testWidgets(
      'submitted buy item renders symbol, order id, KIS ODNO, and submit status',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 7600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(_FakeExecutionReviewApi());

    await tester.pumpWidget(_wrap(controller));
    await _refreshExecutionReview(tester);

    expect(find.textContaining('005930'), findsWidgets);
    expect(find.text('17'), findsOneWidget);
    expect(find.text('OD17'), findsOneWidget);
    expect(find.text('VALIDATION CALLED'), findsOneWidget);
    expect(find.text('MANUAL SUBMIT CALLED'), findsOneWidget);
    expect(find.text('BROKER SUBMIT CALLED'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('blocked item renders primary block reason and broker submit no',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 7600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(_FakeExecutionReviewApi());

    await tester.pumpWidget(_wrap(controller));
    await _refreshExecutionReview(tester);

    expect(find.text('score_threshold_not_met'), findsWidgets);
    expect(find.text('Broker submit: No'), findsOneWidget);
    expect(find.text('Real order submitted: No'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('execution review safety violation renders warning',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 7600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(_FakeExecutionReviewApi(
      review: _executionReview(withViolation: true),
    ));

    await tester.pumpWidget(_wrap(controller));
    await _refreshExecutionReview(tester);

    expect(find.text('Safety Violations'), findsOneWidget);
    expect(find.text('SAFETY VIOLATION'), findsOneWidget);
    expect(
        find.text('submitted_buy_missing_validation_called'), findsOneWidget);
    expect(find.text('Submitted buy is missing validation_called=true.'),
        findsOneWidget);

    controller.dispose();
  });

  testWidgets('execution review raw payload is collapsed by default',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 7600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(_FakeExecutionReviewApi());

    await tester.pumpWidget(_wrap(controller));
    await _refreshExecutionReview(tester);

    final card =
        find.byKey(const Key('kis_limited_auto_buy_execution_review_card'));
    expect(
        find.descendant(of: card, matching: find.text('Developer Raw Payload')),
        findsOneWidget);
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining('"source": "kis_limited_auto_buy"'),
      ),
      findsNothing,
    );

    controller.dispose();
  });
}

DashboardController _controller(_FakeExecutionReviewApi api) {
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

Future<void> _refreshExecutionReview(WidgetTester tester) async {
  final card =
      find.byKey(const Key('kis_limited_auto_buy_execution_review_card'));
  final refresh = find.descendant(
    of: card,
    matching: find.text('Refresh Execution Review'),
  );
  await tester.ensureVisible(refresh);
  await tester.tap(refresh);
  await tester.pumpAndSettle();
}

class _FakeExecutionReviewApi extends ApiClient {
  _FakeExecutionReviewApi({KisLimitedAutoBuyExecutionReview? review})
      : review = review ?? _executionReview();

  KisLimitedAutoBuyExecutionReview review;
  int reviewCalls = 0;

  @override
  Future<KisLimitedAutoBuyExecutionReview>
      fetchKisLimitedAutoBuyExecutionReview({
    int limit = 20,
    int days = 30,
    String? symbol,
    bool includeRaw = false,
  }) async {
    reviewCalls += 1;
    return review;
  }
}

KisLimitedAutoBuyExecutionReview _executionReview({
  bool empty = false,
  bool withViolation = false,
}) {
  return KisLimitedAutoBuyExecutionReview.fromJson(
    _executionReviewJson(empty: empty, withViolation: withViolation),
  );
}

Map<String, dynamic> _executionReviewJson({
  bool empty = false,
  bool withViolation = false,
}) {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_limited_auto_buy_execution_review',
    'source': 'kis_limited_auto_buy',
    'review_only': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'summary': {
      'total_decisions': empty ? 0 : 2,
      'submitted_buy_count': empty ? 0 : 1,
      'blocked_count': empty ? 0 : 1,
      'readiness_only_count': empty ? 0 : 1,
      'validation_failed_count': 0,
      'duplicate_position_block_count': 0,
      'duplicate_open_order_block_count': 0,
      'daily_limit_block_count': 0,
      'cash_block_count': 0,
      'max_notional_block_count': 0,
      'market_session_block_count': 0,
      'no_new_entry_after_block_count': 0,
      'score_block_count': empty ? 0 : 1,
      'sell_pressure_block_count': 0,
      'buy_sell_spread_block_count': 0,
      'no_submit_invariant_ok': true,
      'submitted_rows_have_audit_metadata': true,
      'submitted_rows_have_order_ids': true,
      'submitted_rows_have_kis_odno_count': empty ? 0 : 1,
      'max_daily_buy_count_observed': empty ? 0 : 1,
      'latest_submitted_at': empty ? null : '2026-05-22T01:00:00+00:00',
      'latest_blocked_at': empty ? null : '2026-05-22T01:01:00+00:00',
      'latest_symbol': empty ? null : '005930',
    },
    'submitted_buys': empty ? [] : [_submittedBuy()],
    'blocked_decisions': empty ? [] : [_blockedDecision()],
    'safety_violations': withViolation
        ? [
            {
              'code': 'submitted_buy_missing_validation_called',
              'reason': 'Submitted buy is missing validation_called=true.',
              'severity': 'warning',
              'symbol': '005930',
              'order_id': 17,
            }
          ]
        : [],
    'top_block_reasons': empty
        ? []
        : [
            {
              'reason': 'score_threshold_not_met',
              'count': 1,
              'label': 'Score threshold not met',
            }
          ],
    'daily_usage': empty
        ? []
        : [
            {
              'date': '2026-05-22',
              'submitted_buy_count': 1,
              'symbols': ['005930'],
              'total_estimated_notional': 288000,
              'daily_limit': 1,
              'limit_exceeded': false,
            }
          ],
    'safety': {
      'review_only': true,
      'no_broker_submit_from_review': true,
      'scheduler_real_orders_enabled': false,
      'no_submit_invariant_ok': true,
    },
    'diagnostics': {'order_rows_scanned': empty ? 0 : 1},
  };
}

Map<String, dynamic> _submittedBuy() {
  return {
    'order_id': 17,
    'broker_order_id': 'BRK17',
    'kis_odno': 'OD17',
    'created_at': '2026-05-22T01:00:00+00:00',
    'symbol': '005930',
    'company_name': 'Samsung Electronics',
    'quantity': 4,
    'estimated_notional': 288000,
    'current_price': 72000,
    'final_buy_score': 82.5,
    'required_buy_score': 75,
    'final_sell_score': 12,
    'confidence': 0.76,
    'gate_level': 2,
    'available_cash': 3000000,
    'max_notional_pct': 0.03,
    'runtime_safety_snapshot': {
      'dry_run': false,
      'kill_switch': false,
      'kis_scheduler_allow_real_orders': false,
    },
    'validation_summary': {
      'validated_for_submission': true,
      'current_price': 72000,
    },
    'source': 'kis_limited_auto_buy',
    'source_type': 'guarded_limited_auto_buy',
    'mode': 'kis_limited_auto_buy_run',
    'trigger_source': 'limited_auto_buy_run_once',
    'real_order_submitted': true,
    'broker_submit_called': true,
    'manual_submit_called': true,
    'validation_called': true,
    'broker_status': 'submitted',
    'internal_status': 'SUBMITTED',
  };
}

Map<String, dynamic> _blockedDecision() {
  return {
    'run_id': 8,
    'signal_id': 5,
    'created_at': '2026-05-22T01:01:00+00:00',
    'symbol': '000660',
    'company_name': 'SK Hynix',
    'result': 'blocked',
    'action': 'blocked_buy',
    'primary_block_reason': 'score_threshold_not_met',
    'block_reasons': ['score_threshold_not_met'],
    'final_buy_score': 60,
    'required_buy_score': 75,
    'final_sell_score': 12,
    'confidence': 0.7,
    'estimated_notional': 288000,
    'suggested_quantity': 4,
    'cash_available': 3000000,
    'duplicate_position': false,
    'duplicate_open_order': false,
    'daily_limit_remaining': 1,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
  };
}
