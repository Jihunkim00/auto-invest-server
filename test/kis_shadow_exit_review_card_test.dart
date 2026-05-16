import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_shadow_exit_review.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';

void main() {
  test('fetchKisShadowExitReview calls GET review endpoint with params',
      () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_reviewJson()), 200);
      }),
    );

    final result = await client.fetchKisShadowExitReview(
      days: 14,
      limit: 7,
      symbol: '005930',
    );

    expect(captured.method, 'GET');
    expect(captured.url.path, '/kis/exit-shadow/review');
    expect(captured.url.queryParameters['days'], '14');
    expect(captured.url.queryParameters['limit'], '7');
    expect(captured.url.queryParameters['symbol'], '005930');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/validate')));
    expect(result.mode, 'shadow_exit_review');
  });

  testWidgets('review card shows read-only labels and summary', (tester) async {
    tester.view.physicalSize = const Size(1200, 3000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeReviewApiClient();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('KIS Shadow Exit Review'), findsOneWidget);
    expect(find.text('REVIEW ONLY'), findsOneWidget);
    expect(find.text('SHADOW DECISION QUALITY'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('NO MANUAL SUBMIT'), findsWidgets);
    expect(find.text('LIVE AUTO SELL DISABLED'), findsWidgets);
    expect(find.text('SCHEDULER REAL ORDERS DISABLED'), findsWidgets);
    expect(find.text('Refresh Review only'), findsOneWidget);
    expect(find.text('Enable Auto Sell'), findsNothing);
    expect(find.text('Enable Scheduler Real Orders'), findsNothing);
    expect(find.text('Submit Live KIS Order'), findsNothing);

    await tester.ensureVisible(find.text('Refresh Review only'));
    await tester.tap(find.text('Refresh Review only'));
    await tester.pumpAndSettle();

    expect(api.reviewCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.text('total shadow runs'.toUpperCase()), findsOneWidget);
    expect(find.text('3'), findsWidgets);
    expect(find.text('would sell count'.toUpperCase()), findsOneWidget);
    expect(find.text('hold count'.toUpperCase()), findsOneWidget);
    expect(find.text('manual review count'.toUpperCase()), findsOneWidget);
    expect(find.text('would sell rate'.toUpperCase()), findsOneWidget);
    expect(find.text('33.33%'), findsOneWidget);
    expect(find.text('manual sell followed'.toUpperCase()), findsOneWidget);
    expect(find.text('1 / 100.00%'), findsOneWidget);
    expect(find.text('no-submit invariant'.toUpperCase()), findsOneWidget);
    expect(find.text('No-submit invariant: OK'), findsOneWidget);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('stop_loss'), findsOneWidget);
    expect(find.text('KRW -2,880 / -2.00%'), findsOneWidget);
    expect(find.text('FILLED'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('review card renders missing P/L percent as dash',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(
      _FakeReviewApiClient(
          review: KisShadowExitReview.fromJson(_reviewJson(
        percent: null,
        decision: 'manual_review',
        trigger: 'manual_review',
      ))),
    );

    await tester.pumpWidget(_wrap(controller));
    await tester.ensureVisible(find.text('Refresh Review only'));
    await tester.tap(find.text('Refresh Review only'));
    await tester.pumpAndSettle();

    expect(find.text('KRW -2,880 / --'), findsOneWidget);

    controller.dispose();
  });
}

DashboardController _controller(_FakeReviewApiClient api) {
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
          builder: (context, _) => WatchlistSection(controller: controller),
        ),
      ),
    ),
  );
}

class _FakeReviewApiClient extends ApiClient {
  _FakeReviewApiClient({KisShadowExitReview? review})
      : review = review ?? KisShadowExitReview.fromJson(_reviewJson());

  final KisShadowExitReview review;
  int reviewCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisShadowExitReview> fetchKisShadowExitReview({
    int days = 30,
    int limit = 20,
    String? symbol,
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

Map<String, dynamic> _reviewJson({
  double? percent = -0.02,
  String decision = 'would_sell',
  String trigger = 'stop_loss',
}) {
  return {
    'status': 'ok',
    'mode': 'shadow_exit_review',
    'review_window_days': 30,
    'summary': {
      'total_shadow_runs': 3,
      'would_sell_count': 1,
      'hold_count': 1,
      'manual_review_count': 1,
      'no_candidate_count': 1,
      'stop_loss_count': 1,
      'take_profit_count': 0,
      'manual_review_trigger_count': decision == 'manual_review' ? 1 : 0,
      'insufficient_cost_basis_count': decision == 'manual_review' ? 1 : 0,
      'unique_symbols_evaluated': 3,
      'manual_sell_followed_count': 1,
      'manual_sell_followed_rate': 1.0,
      'unmatched_shadow_would_sell_count': 0,
      'would_sell_rate': 1 / 3,
      'manual_review_rate': 1 / 3,
      'no_submit_invariant_ok': true,
    },
    'recent_decisions': [
      {
        'created_at': '2026-05-15T01:00:00+00:00',
        'run_id': 10,
        'run_key': 'shadow-linked',
        'signal_id': 3,
        'symbol': '005930',
        'decision': decision,
        'action': decision == 'would_sell' ? 'sell' : 'hold',
        'trigger': trigger,
        'trigger_source': 'cost_basis_pl_pct',
        'unrealized_pl': -2880,
        'unrealized_pl_pct': percent,
        'cost_basis': 144000,
        'current_value': 141120,
        'suggested_quantity': 2,
        'reason': 'Shadow decision only.',
        'risk_flags': ['stop_loss_triggered'],
        'gating_notes': ['no_broker_submit'],
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'linked_manual_order_id': 44,
        'linked_manual_order_status': 'FILLED',
      }
    ],
    'safety': {
      'read_only': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
      'no_submit_invariant_ok': true,
    },
    'created_at': '2026-05-15T01:05:00+00:00',
  };
}
