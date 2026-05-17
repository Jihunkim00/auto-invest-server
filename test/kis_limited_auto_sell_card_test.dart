import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_limited_auto_sell.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('runKisLimitedAutoSellOnce calls limited auto sell endpoint', () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_limitedAutoSellJson()), 200);
      }),
    );

    final result = await client.runKisLimitedAutoSellOnce();

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/limited-auto-sell/run-once');
    expect(captured.body, '{}');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/validate')));
    expect(result.mode, 'limited_auto_sell');
  });

  testWidgets('limited auto sell card shows guarded disabled state',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeLimitedAutoSellApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    final limitedAutoSellCard =
        find.byKey(const Key('kis_limited_auto_sell_card'));
    expect(limitedAutoSellCard, findsOneWidget);
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('KIS Limited Auto Sell'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
          of: limitedAutoSellCard, matching: find.text('SELL ONLY')),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('DISABLED BY DEFAULT'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('STOP-LOSS ONLY'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('NO AUTO BUY'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('SCHEDULER REAL ORDERS DISABLED'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('GUARDED EXECUTION'),
      ),
      findsOneWidget,
    );
    final runButton = find.descendant(
      of: limitedAutoSellCard,
      matching: find.text('Run Limited Auto Sell Once'),
    );
    expect(runButton, findsOneWidget);
    expect(find.text('Auto Buy'), findsNothing);
    expect(find.text('Enable Scheduler Real Orders'), findsNothing);
    expect(find.text('Enable Take Profit Auto Sell'), findsNothing);

    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.text('limited_auto_sell_disabled'), findsWidgets);
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('REAL_ORDER_SUBMITTED'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('BROKER_SUBMIT_CALLED'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('MANUAL_SUBMIT_CALLED'),
      ),
      findsOneWidget,
    );
    expect(find.text('LIVE SELL SUBMITTED'), findsNothing);

    controller.dispose();
  });

  testWidgets('limited auto sell card warns when backend submitted',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(
      _FakeLimitedAutoSellApi(
        result: KisLimitedAutoSell.fromJson(_limitedAutoSellJson(
          submitted: true,
        )),
      ),
    );

    await tester.pumpWidget(_wrap(controller));
    await tester.ensureVisible(find.text('Run Limited Auto Sell Once'));
    await tester.tap(find.text('Run Limited Auto Sell Once'));
    await tester.pumpAndSettle();

    expect(find.textContaining('LIVE SELL SUBMITTED'), findsOneWidget);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('stop_loss'), findsWidgets);
    expect(find.text('KRW -4,000 / -4.00%'), findsOneWidget);
    expect(find.text('AUTO123'), findsWidgets);

    controller.dispose();
  });
}

DashboardController _controller(_FakeLimitedAutoSellApi api) {
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

class _FakeLimitedAutoSellApi extends ApiClient {
  _FakeLimitedAutoSellApi({KisLimitedAutoSell? result})
      : result = result ?? KisLimitedAutoSell.fromJson(_limitedAutoSellJson());

  KisLimitedAutoSell result;
  int runCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisLimitedAutoSell> runKisLimitedAutoSellOnce() async {
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

Map<String, dynamic> _limitedAutoSellJson({bool submitted = false}) {
  return {
    'status': 'ok',
    'mode': 'limited_auto_sell',
    'result': submitted ? 'submitted' : 'blocked',
    'action': submitted ? 'sell' : 'hold',
    'reason': submitted
        ? 'Limited auto sell submitted for stop-loss after all safety gates passed.'
        : 'limited_auto_sell_disabled',
    'symbol': submitted ? '005930' : null,
    'quantity': submitted ? 1 : null,
    'trigger': submitted ? 'stop_loss' : null,
    'trigger_source': submitted ? 'cost_basis_pl_pct' : null,
    'order_id': submitted ? 123 : null,
    'broker_order_id': submitted ? 'AUTO123' : null,
    'kis_odno': submitted ? 'AUTO123' : null,
    'unrealized_pl': submitted ? -4000 : null,
    'unrealized_pl_pct': submitted ? -0.04 : null,
    'real_order_submitted': submitted,
    'broker_submit_called': submitted,
    'manual_submit_called': false,
    'auto_buy_enabled': false,
    'auto_sell_enabled': submitted,
    'scheduler_real_order_enabled': false,
    'checks': {
      'kis_limited_auto_sell_enabled': submitted,
      'kis_limited_auto_sell_stop_loss_enabled': submitted,
      'queue_review_required': true,
    },
    'blocked_by': submitted ? const [] : ['limited_auto_sell_disabled'],
    'safety': {
      'max_orders_per_day': 1,
      'max_notional_pct': 0.03,
      'stop_loss_only': true,
      'take_profit_auto_sell_enabled': false,
      'manual_review_auto_sell_enabled': false,
      'auto_buy_enabled': false,
      'scheduler_real_order_enabled': false,
    },
    'audit_metadata': {
      'source': 'kis_limited_auto_sell',
      'source_type': 'guarded_stop_loss_exit',
    },
  };
}
