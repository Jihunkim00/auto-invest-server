import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_limited_auto_buy.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('runKisLimitedAutoBuyOnce calls limited auto buy endpoint', () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_limitedAutoBuyJson()), 200);
      }),
    );

    final result = await client.runKisLimitedAutoBuyOnce();

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/limited-auto-buy/run-once');
    expect(captured.body, '{}');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/validate')));
    expect(result.mode, 'limited_auto_buy');
  });

  testWidgets('limited auto buy card shows guarded disabled state',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 4200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeLimitedAutoBuyApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_limited_auto_buy_card'));
    expect(card, findsOneWidget);
    expect(
      find.descendant(of: card, matching: find.text('KIS Limited Auto Buy')),
      findsOneWidget,
    );
    for (final label in [
      'BUY ONLY',
      'DISABLED BY DEFAULT',
      'NO AUTO BUY UNLESS ENABLED',
      'RISK GATED',
      'POSITION CAPPED',
      'SCHEDULER REAL ORDERS DISABLED',
    ]) {
      expect(
        find.descendant(of: card, matching: find.text(label)),
        findsOneWidget,
      );
    }
    expect(find.text('Enable Auto Buy'), findsNothing);
    expect(find.text('Submit Buy'), findsNothing);
    expect(find.text('Enable Scheduler Real Orders'), findsNothing);

    final runButton = find.descendant(
      of: card,
      matching: find.text('Run Limited Auto Buy Once'),
    );
    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.text('limited_auto_buy_disabled'), findsWidgets);
    expect(find.text('LIVE BUY SUBMITTED'), findsNothing);

    controller.dispose();
  });

  testWidgets('limited auto buy card warns when backend submitted',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 4200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(
      _FakeLimitedAutoBuyApi(
        result:
            KisLimitedAutoBuy.fromJson(_limitedAutoBuyJson(submitted: true)),
      ),
    );

    await tester.pumpWidget(_wrap(controller));
    final runButton = find.descendant(
      of: find.byKey(const Key('kis_limited_auto_buy_card')),
      matching: find.text('Run Limited Auto Buy Once'),
    );
    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(find.textContaining('LIVE BUY SUBMITTED'), findsOneWidget);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('KRW 216,000'), findsOneWidget);
    expect(find.text('BUY123'), findsWidgets);

    controller.dispose();
  });
}

DashboardController _controller(_FakeLimitedAutoBuyApi api) {
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

class _FakeLimitedAutoBuyApi extends ApiClient {
  _FakeLimitedAutoBuyApi({KisLimitedAutoBuy? result})
      : result = result ?? KisLimitedAutoBuy.fromJson(_limitedAutoBuyJson());

  KisLimitedAutoBuy result;
  int runCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisLimitedAutoBuy> runKisLimitedAutoBuyOnce({int? gateLevel}) async {
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

Map<String, dynamic> _limitedAutoBuyJson({bool submitted = false}) {
  return {
    'status': 'ok',
    'mode': 'limited_auto_buy',
    'result': submitted ? 'submitted' : 'blocked',
    'action': submitted ? 'buy' : 'hold',
    'reason': submitted
        ? 'Limited auto buy submitted after all safety gates passed.'
        : 'limited_auto_buy_disabled',
    'symbol': submitted ? '005930' : null,
    'quantity': submitted ? 3 : null,
    'notional': submitted ? 216000 : null,
    'final_score': submitted ? 82.5 : null,
    'confidence': submitted ? 0.76 : null,
    'order_id': submitted ? 123 : null,
    'broker_order_id': submitted ? 'BUY123' : null,
    'kis_odno': submitted ? 'BUY123' : null,
    'real_order_submitted': submitted,
    'broker_submit_called': submitted,
    'manual_submit_called': false,
    'auto_buy_enabled': submitted,
    'scheduler_real_order_enabled': false,
    'checks': {'kis_limited_auto_buy_enabled': submitted},
    'safety': {
      'max_orders_per_day': 1,
      'max_notional_pct': 0.03,
      'max_positions': 3,
    },
    'audit_metadata': {'source': 'kis_limited_auto_buy'},
  };
}
