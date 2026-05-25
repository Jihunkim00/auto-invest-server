import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_limited_auto_buy_review.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';

void main() {
  test('limited buy review API calls review endpoint', () async {
    final paths = <String>[];
    final client = ApiClient(
      client: MockClient((request) async {
        paths.add('${request.method} ${request.url.path}');
        return http.Response(jsonEncode(_reviewJson()), 200);
      }),
    );

    final review = await client.fetchKisLimitedAutoBuyReview();

    expect(paths, ['GET /kis/limited-auto-buy/review']);
    expect(review.mode, 'kis_limited_auto_buy_review');
    expect(review.reviewOnly, isTrue);
  });

  testWidgets('limited buy review card renders empty state', (tester) async {
    tester.view.physicalSize = const Size(1200, 4400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(_FakeReviewApi());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_limited_auto_buy_review_card'));
    expect(card, findsOneWidget);
    for (final label in [
      'BUY REVIEW ONLY',
      'READINESS QUALITY',
      'NO BROKER SUBMIT',
      'AUTO BUY DISABLED',
      'SCHEDULER REAL ORDERS DISABLED',
    ]) {
      expect(find.descendant(of: card, matching: find.text(label)),
          findsOneWidget);
    }
    expect(
      find.text(
        'No limited buy readiness decisions yet. Run Buy Preflight or Run Limited Buy Once to generate review data.',
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets(
      'limited buy review renders summary, decisions, and collapsed raw',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 5600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeReviewApi(review: _review());
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    final card = find.byKey(const Key('kis_limited_auto_buy_review_card'));
    final refresh = find.descendant(
      of: card,
      matching: find.text('Refresh Review'),
    );
    await tester.ensureVisible(refresh);
    await tester.tap(refresh);
    await tester.pumpAndSettle();

    expect(api.reviewCalls, 1);
    expect(find.text('BUY READY COUNT'), findsOneWidget);
    expect(find.text('BLOCKED COUNT'), findsOneWidget);
    expect(find.text('Score threshold not met: 1'), findsOneWidget);
    expect(find.text('005930 · Samsung Electronics'), findsWidgets);
    expect(find.text('BUY_READY'), findsOneWidget);
    expect(find.text('82.5 / 75'), findsOneWidget);
    expect(find.text('buy_readiness_only'), findsOneWidget);
    expect(find.text('Broker submit: No'), findsOneWidget);
    expect(find.text('Real order submitted: No'), findsOneWidget);
    expect(find.text('Developer Raw Payload'), findsOneWidget);
    expect(
      find.textContaining('"source": "kis_limited_auto_buy"'),
      findsNothing,
    );

    controller.dispose();
  });
}

DashboardController _controller(_FakeReviewApi api) {
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

class _FakeReviewApi extends ApiClient {
  _FakeReviewApi({KisLimitedAutoBuyReview? review})
      : review = review ?? KisLimitedAutoBuyReview.fromJson(_reviewJson());

  KisLimitedAutoBuyReview review;
  int reviewCalls = 0;

  @override
  Future<KisLimitedAutoBuyReview> fetchKisLimitedAutoBuyReview({
    int limit = 20,
    int days = 30,
    String? symbol,
    bool includeRaw = false,
  }) async {
    reviewCalls += 1;
    return review;
  }
}

KisLimitedAutoBuyReview _review() {
  return KisLimitedAutoBuyReview.fromJson(_reviewJson());
}

Map<String, dynamic> _reviewJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_limited_auto_buy_review',
    'source': 'kis_limited_auto_buy',
    'review_only': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'summary': {
      'total_runs': 2,
      'buy_ready_count': 1,
      'blocked_count': 1,
      'no_candidate_count': 0,
      'insufficient_cash_count': 0,
      'score_threshold_not_met_count': 1,
      'sell_pressure_too_high_count': 0,
      'duplicate_position_count': 0,
      'duplicate_open_order_count': 0,
      'daily_limit_reached_count': 0,
      'market_session_block_count': 0,
      'no_new_entry_after_block_count': 0,
      'missing_indicators_count': 0,
      'avg_final_buy_score': 82.5,
      'avg_final_sell_score': 12,
      'avg_required_buy_score': 75,
      'avg_confidence': 0.76,
      'latest_run_at': '2026-05-22T01:00:00+00:00',
      'latest_candidate_symbol': '005930',
      'latest_candidate_company': 'Samsung Electronics',
      'no_submit_invariant_ok': true,
    },
    'recent_decisions': [_decision()],
    'top_block_reasons': [
      {
        'reason': 'score_threshold_not_met',
        'count': 1,
        'label': 'Score threshold not met',
      }
    ],
    'latest_buy_ready': _decision(),
    'safety': {
      'review_only': true,
      'no_order_log_created': true,
      'no_submit_invariant_ok': true,
    },
    'diagnostics': {'rows_scanned': 2},
  };
}

Map<String, dynamic> _decision() {
  return {
    'run_id': 7,
    'signal_id': 5,
    'created_at': '2026-05-22T01:00:00+00:00',
    'trigger_source': 'limited_auto_buy_run_once',
    'symbol': '005930',
    'company_name': 'Samsung Electronics',
    'result': 'readiness_only',
    'action': 'buy_ready',
    'status': 'BUY_READY',
    'final_buy_score': 82.5,
    'required_buy_score': 75,
    'final_sell_score': 12,
    'confidence': 0.76,
    'buy_sell_spread': 70.5,
    'estimated_notional': 288000,
    'suggested_quantity': 4,
    'cash_available': 3000000,
    'block_reasons': ['auto_buy_execution_disabled'],
    'primary_block_reason': 'auto_buy_execution_disabled',
    'reason': 'buy_readiness_only',
    'gate_level': 2,
    'duplicate_position': false,
    'duplicate_open_order': false,
    'market_session_allowed': true,
    'no_new_entry_after_blocked': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
  };
}
