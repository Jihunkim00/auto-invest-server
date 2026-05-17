import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_buy_shadow_decision.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('runKisBuyShadowOnce calls buy shadow endpoint', () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_buyShadowJson()), 200);
      }),
    );

    final result = await client.runKisBuyShadowOnce();

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/buy-shadow/run-once');
    expect(captured.body, '{}');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/validate')));
    expect(result.mode, 'shadow_buy_dry_run');
  });

  testWidgets('buy shadow card shows shadow-only guarded state',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeBuyShadowApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_buy_shadow_decision_card'));
    expect(card, findsOneWidget);
    expect(
      find.descendant(of: card, matching: find.text('KIS Buy Shadow Decision')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: card, matching: find.text('SHADOW BUY ONLY')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: card, matching: find.text('NO BROKER SUBMIT')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: card, matching: find.text('NO MANUAL SUBMIT')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: card, matching: find.text('LIVE AUTO BUY DISABLED')),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: card,
        matching: find.text('SCHEDULER REAL ORDERS DISABLED'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(of: card, matching: find.text('RISK GATED')),
      findsOneWidget,
    );

    final runButton = find.descendant(
      of: card,
      matching: find.text('Run Buy Shadow Once'),
    );
    expect(runButton, findsOneWidget);
    expect(find.text('Auto Buy'), findsNothing);
    expect(find.text('Enable Auto Buy'), findsNothing);
    expect(find.text('Submit Buy'), findsNothing);
    expect(find.text('Enable Scheduler Real Orders'), findsNothing);

    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.text('WOULD BUY'), findsWidgets);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('82.5'), findsWidgets);
    expect(find.text('0.8'), findsWidgets);
    expect(find.text('78'), findsWidgets);
    expect(find.text('KRW 288,000'), findsOneWidget);
    expect(find.text('4'), findsWidgets);
    expect(find.text('LIVE BUY SUBMITTED'), findsNothing);

    controller.dispose();
  });

  testWidgets('buy shadow card displays hold reason safely', (tester) async {
    tester.view.physicalSize = const Size(1200, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(
      _FakeBuyShadowApi(
        result: KisBuyShadowDecision.fromJson(_buyShadowJson(hold: true)),
      ),
    );

    await tester.pumpWidget(_wrap(controller));
    final runButton = find.descendant(
      of: find.byKey(const Key('kis_buy_shadow_decision_card')),
      matching: find.text('Run Buy Shadow Once'),
    );
    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(find.text('HOLD'), findsWidgets);
    expect(find.text('score_threshold_not_met'), findsWidgets);
    expect(find.text('Submit Buy'), findsNothing);

    controller.dispose();
  });
}

DashboardController _controller(_FakeBuyShadowApi api) {
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

class _FakeBuyShadowApi extends ApiClient {
  _FakeBuyShadowApi({KisBuyShadowDecision? result})
      : result = result ?? KisBuyShadowDecision.fromJson(_buyShadowJson());

  KisBuyShadowDecision result;
  int runCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisBuyShadowDecision> runKisBuyShadowOnce() async {
    runCalls += 1;
    return result;
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

Map<String, dynamic> _buyShadowJson({bool hold = false}) {
  return {
    'status': 'ok',
    'mode': 'shadow_buy_dry_run',
    'decision': hold ? 'hold' : 'would_buy',
    'action': hold ? 'hold' : 'buy',
    'reason': hold
        ? 'score_threshold_not_met'
        : 'Shadow buy candidate only. No broker submit.',
    'symbol': hold ? null : '005930',
    'candidate': hold
        ? null
        : {
            'symbol': '005930',
            'market': 'KR',
            'provider': 'kis',
            'final_score': 82.5,
            'confidence': 0.76,
            'quant_score': 78,
            'gpt_buy_score': 65,
            'current_price': 72000,
            'suggested_notional': 288000,
            'suggested_quantity': 4,
            'reason': 'candidate',
            'risk_flags': ['shadow_buy_only'],
            'gating_notes': [
              'shadow_buy_only',
              'no_broker_submit',
              'live_auto_buy_disabled',
            ],
            'audit_metadata': {'source': 'kis_buy_shadow_decision'},
          },
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'auto_buy_enabled': false,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'checks': {
      'kis_limited_auto_buy_shadow_enabled': true,
      'kis_limited_auto_buy_enabled': false,
    },
    'safety': {'read_only': true},
    'risk_flags': ['shadow_buy_only'],
    'gating_notes': ['no_broker_submit'],
    'failed_checks': hold ? ['score_threshold'] : const [],
    'created_at': '2026-05-17T10:00:00Z',
  };
}
