import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('runKisSchedulerDryRunOnce posts scheduler endpoint only', () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_runJson()), 200);
      }),
    );

    final result = await client.runKisSchedulerDryRunOnce();

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/scheduler/run-dry-run-auto-once');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/submit-manual')));
    expect(captured.body, '{}');
    expect(captured.body, isNot(contains('999999')));
    expect(captured.body, isNot(contains('symbol')));
    expect(captured.body, isNot(contains('qty')));
    expect(captured.body, isNot(contains('side')));
    expect(result.realOrderSubmitted, isFalse);
  });

  testWidgets('KIS scheduler status panel shows simulation-only state',
      (tester) async {
    final controller = _schedulerController(_FakeSchedulerApiClient())
      ..kisSchedulerStatusLoaded = true;

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('KIS Scheduler Simulation'), findsOneWidget);
    expect(find.text('DISABLED BY DEFAULT'), findsOneWidget);
    expect(find.text('DRY-RUN ONLY'), findsOneWidget);
    expect(find.text('REAL ORDER SCHEDULER DISABLED'), findsOneWidget);
    expect(find.text('real_orders_allowed=false'), findsOneWidget);
    expect(find.text('ENABLED'), findsOneWidget);
    expect(find.text('DRY_RUN'), findsOneWidget);
    expect(find.text('ALLOW_REAL_ORDERS'), findsOneWidget);
    expect(find.text('REAL_ORDERS_ALLOWED'), findsOneWidget);
    expect(find.text('REAL_ORDER_SCHEDULER_ENABLED'), findsOneWidget);
    expect(find.text('RUNTIME_SCHEDULER_ENABLED'), findsOneWidget);
    expect(find.text('RUNTIME_DRY_RUN'), findsOneWidget);
    expect(find.text('KILL_SWITCH'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Run KIS Scheduler Dry-Run Once shows safety result',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerApiClient();
    final controller = _schedulerController(api)
      ..kisSchedulerStatusLoaded = true
      ..orderTicketSymbol = '999999';

    await tester.pumpWidget(_wrap(controller));

    await tester.ensureVisible(find.text('Run KIS Scheduler Dry-Run Once'));
    await tester.tap(find.text('Run KIS Scheduler Dry-Run Once'));
    await tester.pumpAndSettle();

    expect(api.schedulerRunCalls, 1);
    expect(api.validationCalls, 0);
    expect(controller.kisSchedulerRunResult?.triggeredSymbol, '005930');
    expect(controller.kisSchedulerRunResult?.realOrderSubmitted, isFalse);
    expect(controller.kisSchedulerRunResult?.brokerSubmitCalled, isFalse);
    expect(controller.kisSchedulerRunResult?.manualSubmitCalled, isFalse);
    expect(find.text('real_order_submitted=false'), findsOneWidget);
    expect(find.text('broker_submit_called=false'), findsOneWidget);
    expect(find.text('manual_submit_called=false'), findsOneWidget);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('simulated_order_created'), findsWidgets);
    expect(find.text('buy'), findsWidgets);
    expect(find.text('dry_run_risk_approved'), findsWidgets);
    expect(find.text('123'), findsOneWidget);
    expect(find.text('456'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('KIS scheduler run error shows concise retry message',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerApiClient(throwRun: true);
    final controller = _schedulerController(api)
      ..kisSchedulerStatusLoaded = true;

    await tester.pumpWidget(_wrap(controller));

    await tester.ensureVisible(find.text('Run KIS Scheduler Dry-Run Once'));
    await tester.tap(find.text('Run KIS Scheduler Dry-Run Once'));
    await tester.pumpAndSettle();

    expect(api.schedulerRunCalls, 1);
    expect(find.text('Scheduler failed'), findsWidgets);
    expect(find.text('Retry'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('KIS scheduler status refresh and retry reload status',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerApiClient(throwStatus: true);
    final controller = _schedulerController(api);

    await tester.pumpWidget(_wrap(controller));

    await tester.tap(find.byTooltip('Refresh KIS scheduler status'));
    await tester.pumpAndSettle();

    expect(api.statusCalls, 1);
    expect(find.text('Status unavailable'), findsWidgets);
    expect(find.text('Retry'), findsOneWidget);

    api.throwStatus = false;
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();

    expect(api.statusCalls, 2);
    expect(controller.kisSchedulerStatusLoaded, isTrue);
    expect(find.text('Retry'), findsNothing);
    expect(find.text('Status unavailable'), findsNothing);

    controller.dispose();
  });
}

DashboardController _schedulerController(_FakeSchedulerApiClient api) {
  return DashboardController(api, autoload: false)
    ..selectedProvider = SelectedProvider.kis
    ..krWatchlist = _krWatchlist
    ..kisSchedulerStatus = _status();
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

class _FakeSchedulerApiClient extends ApiClient {
  _FakeSchedulerApiClient({
    this.throwStatus = false,
    this.throwRun = false,
  });

  bool throwStatus;
  bool throwRun;
  int statusCalls = 0;
  int schedulerRunCalls = 0;
  int validationCalls = 0;

  @override
  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async {
    statusCalls += 1;
    if (throwStatus) {
      throw const ApiRequestException(
        'HTTP 503: {"message":"Status unavailable"}',
      );
    }
    return _status();
  }

  @override
  Future<KisSchedulerRunResult> runKisSchedulerDryRunOnce() async {
    schedulerRunCalls += 1;
    if (throwRun) {
      throw const ApiRequestException(
        'HTTP 503: {"message":"Scheduler failed"}',
      );
    }
    return KisSchedulerRunResult.fromJson(_runJson());
  }

  @override
  Future<List<TradingRun>> getRecentTradingRuns() async => const [];

  @override
  Future<List<KisManualOrderResult>> fetchKisOrders({
    int limit = 20,
    bool includeRejected = false,
  }) async {
    return const [];
  }

  @override
  Future<KisOrderSummary> fetchKisOrderSummary() async {
    return KisOrderSummary.empty;
  }

  @override
  Future<OrderValidationResult> validateKisOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
  }) async {
    validationCalls += 1;
    return OrderValidationResult(
      provider: 'kis',
      market: 'KR',
      environment: 'prod',
      dryRun: true,
      validatedForSubmission: true,
      canSubmitLater: true,
      symbol: symbol,
      side: side,
      qty: qty,
      orderType: orderType,
      currentPrice: 72000,
      estimatedAmount: 72000,
      availableCash: 1000000,
      heldQty: null,
      warnings: const [],
      blockReasons: const [],
      marketSession: const MarketSessionStatus(
        market: 'KR',
        timezone: 'Asia/Seoul',
        isMarketOpen: true,
        isEntryAllowedNow: true,
        isNearClose: false,
      ),
      orderPreview: const OrderPreview(
        accountNoMasked: '12****78',
        productCode: '01',
        symbol: '005930',
        side: 'buy',
        qty: 1,
        orderType: 'market',
        kisTrIdPreview: 'TTTC0802U',
        payloadPreview: {'PDNO': '005930'},
      ),
    );
  }
}

KisSchedulerSimulationStatus _status() {
  return const KisSchedulerSimulationStatus(
    provider: 'kis',
    market: 'KR',
    enabled: false,
    dryRun: true,
    schedulerDryRun: true,
    allowRealOrders: false,
    configuredAllowRealOrders: false,
    realOrdersAllowed: false,
    realOrderSchedulerEnabled: false,
    runtimeSchedulerEnabled: false,
    runtimeDryRun: true,
    killSwitch: false,
    realOrderSubmitted: false,
    brokerSubmitCalled: false,
    manualSubmitCalled: false,
  );
}

Map<String, dynamic> _runJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_scheduler_dry_run_auto',
    'dry_run': true,
    'simulated': true,
    'scheduler_enabled': false,
    'scheduler_dry_run': true,
    'scheduler_allow_real_orders': false,
    'configured_allow_real_orders': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'trigger_source': 'scheduler_kis_dry_run_auto',
    'trigger_sources': [
      'scheduler_kis_dry_run_auto',
      'scheduler_kis_portfolio_simulation',
    ],
    'result': 'simulated_order_created',
    'action': 'buy',
    'triggered_symbol': '005930',
    'signal_id': 123,
    'order_id': 456,
    'reason': 'dry_run_risk_approved',
    'quant_buy_score': 74,
    'ai_buy_score': 82,
    'final_entry_score': 76,
  };
}

const _krWatchlist = MarketWatchlist(
  market: 'KR',
  currency: 'KRW',
  timezone: 'Asia/Seoul',
  watchlistFile: 'config/watchlist_kr.yaml',
  count: 1,
  symbols: [
    WatchlistSymbol(symbol: '005930', name: 'Samsung', market: 'KOSPI'),
  ],
);
