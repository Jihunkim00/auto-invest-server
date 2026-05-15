import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_live_exit_preflight.dart';
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

  test('runKisLiveExitPreflight posts preflight endpoint with empty body',
      () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_exitPreflightJson()), 200);
      }),
    );

    final result = await client.runKisLiveExitPreflight();

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/live-exit/preflight-once');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/submit-manual')));
    expect(captured.body, '{}');
    expect(captured.body, isNot(contains('symbol')));
    expect(captured.body, isNot(contains('qty')));
    expect(captured.body, isNot(contains('side')));
    expect(result.action, 'sell');
    expect(result.realOrderSubmitted, isFalse);
    expect(result.unrealizedPlPct, -0.02);
  });

  test('runKisDryRunAuto posts auto endpoint without manual order payload',
      () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_autoJson()), 200);
      }),
    );

    final result = await client.runKisDryRunAuto(gateLevel: 7);

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/auto/dry-run-once');
    expect(captured.url.queryParameters['gate_level'], '7');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
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
    expect(find.text('KIS Live Exit Manual Confirm'), findsOneWidget);
    expect(find.text('EXIT PREFLIGHT ONLY'), findsOneWidget);
    expect(find.text('MANUAL CONFIRM SELL'), findsOneWidget);
    expect(find.text('NO AUTO SELL'), findsWidgets);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('SCHEDULER REAL ORDERS DISABLED'), findsWidgets);
    expect(find.text('LIVE AUTO REMAINS DISABLED'), findsOneWidget);
    expect(find.text('Run Exit Preflight'), findsOneWidget);
    expect(find.text('DISABLED BY DEFAULT'), findsOneWidget);
    expect(find.text('DRY-RUN ONLY'), findsOneWidget);
    expect(find.text('REAL ORDER SCHEDULER DISABLED'), findsOneWidget);
    expect(find.text('real_orders_allowed=false'), findsOneWidget);
    expect(find.text('ENABLED'), findsOneWidget);
    expect(find.text('DRY_RUN'), findsWidgets);
    expect(find.text('ALLOW_REAL_ORDERS'), findsOneWidget);
    expect(find.text('REAL_ORDERS_ALLOWED'), findsOneWidget);
    expect(find.text('REAL_ORDER_SCHEDULER_ENABLED'), findsOneWidget);
    expect(find.text('RUNTIME_SCHEDULER_ENABLED'), findsOneWidget);
    expect(find.text('RUNTIME_DRY_RUN'), findsOneWidget);
    expect(find.text('KILL_SWITCH'), findsWidgets);
    expect(find.text('Submit Live KIS Order'), findsNothing);

    controller.dispose();
  });

  testWidgets(
      'Run Exit Preflight displays sell candidate without submit button',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerApiClient();
    final controller = _schedulerController(api)
      ..kisSchedulerStatusLoaded = true
      ..orderTicketSymbol = '999999';

    await tester.pumpWidget(_wrap(controller));

    await tester.ensureVisible(find.text('Run Exit Preflight'));
    await tester.tap(find.text('Run Exit Preflight'));
    await tester.pumpAndSettle();

    expect(api.exitPreflightCalls, 1);
    expect(api.validationCalls, 0);
    expect(
      find.text(
        'Exit candidate found. Manual confirmation is required before any live sell order.',
      ),
      findsOneWidget,
    );
    expect(find.text('sell'), findsWidgets);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('2'), findsWidgets);
    expect(find.text('₩141,120'), findsWidgets);
    expect(find.text('-₩2,880'), findsWidgets);
    expect(find.text('-2.00%'), findsWidgets);
    expect(find.text('stop_loss'), findsWidgets);
    expect(find.text('stop_loss_triggered'), findsWidgets);
    expect(find.text('true'), findsWidgets);
    expect(
      find.textContaining('live_scheduler_orders_disabled'),
      findsOneWidget,
    );
    expect(find.textContaining('preflight_only'), findsWidgets);
    expect(find.text('real_order_submitted=false'), findsWidgets);
    expect(find.text('broker_submit_called=false'), findsWidgets);
    expect(find.text('manual_submit_called=false'), findsWidgets);
    expect(find.text('real_order_submit_allowed=false'), findsWidgets);
    expect(find.text('manual_confirm_required=true'), findsWidgets);
    expect(find.text('Prepare Manual Sell Ticket'), findsOneWidget);
    expect(find.text('Submit Live KIS Order'), findsNothing);

    await tester.ensureVisible(find.text('Prepare Manual Sell Ticket'));
    await tester.tap(find.text('Prepare Manual Sell Ticket'));
    await tester.pumpAndSettle();

    expect(api.validationCalls, 0);
    expect(controller.orderTicketSymbol, '005930');
    expect(controller.orderTicketSide, 'sell');
    expect(controller.orderTicketQty, 2);
    expect(controller.orderTicketQtyInput, '2');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderTicketSourceMetadata?['source'],
        'kis_live_exit_preflight');
    expect(controller.orderTicketSourceMetadata?['source_type'],
        'manual_confirm_exit');
    expect(controller.orderTicketSourceMetadata?['exit_trigger'], 'stop_loss');
    expect(controller.orderTicketSourceMetadata?['trigger_source'],
        'cost_basis_pl_pct');
    expect(controller.orderTicketSourceMetadata?['current_price'], 70560);
    expect(controller.orderTicketSourceMetadata?['suggested_quantity'], 2);
    expect(controller.orderTicketSourceMetadata?['preflight_checked_at'],
        '2026-05-14T01:00:00Z');
    expect(controller.orderTicketSourceMetadata?['preflight_run_key'],
        'kis_live_exit_preflight_abcd1234');
    expect(controller.orderTicketSourceMetadata?['preflight_id'], 42);
    expect(controller.orderTicketSourceMetadata?['real_order_submit_allowed'],
        isFalse);

    controller.dispose();
  });

  testWidgets('Exit preflight displays no held position state', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerApiClient(
      exitPreflightPayload: _noHeldExitPreflightJson(),
    );
    final controller = _schedulerController(api)
      ..kisSchedulerStatusLoaded = true;

    await tester.pumpWidget(_wrap(controller));

    await tester.ensureVisible(find.text('Run Exit Preflight'));
    await tester.tap(find.text('Run Exit Preflight'));
    await tester.pumpAndSettle();

    expect(api.exitPreflightCalls, 1);
    expect(find.text('No held KIS position to evaluate.'), findsOneWidget);
    expect(find.text('hold'), findsWidgets);
    expect(find.text('n/a'), findsWidgets);
    expect(find.textContaining('no_held_position'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Exit preflight displays KRW profit and percent separately',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerApiClient(
      exitPreflightPayload: _smallProfitHoldExitPreflightJson(),
    );
    final controller = _schedulerController(api)
      ..kisSchedulerStatusLoaded = true;

    await tester.pumpWidget(_wrap(controller));

    await tester.ensureVisible(find.text('Run Exit Preflight'));
    await tester.tap(find.text('Run Exit Preflight'));
    await tester.pumpAndSettle();

    expect(find.text('₩26'), findsOneWidget);
    expect(find.text('+0.26%'), findsOneWidget);
    expect(find.text('manual_review_required'), findsWidgets);
    expect(find.textContaining('take_profit_triggered'), findsNothing);
    expect(find.text('EXIT PREFLIGHT ONLY'), findsOneWidget);
    expect(find.text('MANUAL CONFIRM SELL'), findsOneWidget);
    expect(find.text('NO AUTO SELL'), findsWidgets);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('LIVE AUTO REMAINS DISABLED'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Exit candidate with unsafe P/L percent displays dashes',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerApiClient(
      exitPreflightPayload: _unsafePlExitPreflightJson(),
    );
    final controller = _schedulerController(api)
      ..kisSchedulerStatusLoaded = true;

    await tester.pumpWidget(_wrap(controller));

    await tester.ensureVisible(find.text('Run Exit Preflight'));
    await tester.tap(find.text('Run Exit Preflight'));
    await tester.pumpAndSettle();

    expect(find.text('risk_exit'), findsWidgets);
    expect(find.text('--'), findsWidgets);
    expect(find.text('NO AUTO SELL'), findsWidgets);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);

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
    expect(find.text('real_order_submitted=false'), findsWidgets);
    expect(find.text('broker_submit_called=false'), findsWidgets);
    expect(find.text('manual_submit_called=false'), findsWidgets);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('simulated_order_created'), findsWidgets);
    expect(find.text('buy'), findsWidgets);
    expect(find.text('dry_run_risk_approved'), findsWidgets);
    expect(find.text('GPT Advisory Context - Preview Only - No Broker Submit'),
        findsOneWidget);
    expect(find.text('AI_BUY_SCORE'), findsOneWidget);
    expect(find.text('AI_SELL_SCORE'), findsOneWidget);
    expect(
        find.text('gpt_reason: KR scheduler advisory context'), findsOneWidget);
    expect(find.textContaining('GPT approved'), findsNothing);
    expect(find.text('123'), findsOneWidget);
    expect(find.text('456'), findsOneWidget);
    expect(find.text('05-08 00:00 (KST 09:00)'), findsOneWidget);

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
    this.exitPreflightPayload,
  });

  bool throwStatus;
  bool throwRun;
  Map<String, dynamic>? exitPreflightPayload;
  int statusCalls = 0;
  int schedulerRunCalls = 0;
  int exitPreflightCalls = 0;
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
  Future<KisLiveExitPreflightResult> runKisLiveExitPreflight() async {
    exitPreflightCalls += 1;
    return KisLiveExitPreflightResult.fromJson(
      exitPreflightPayload ?? _exitPreflightJson(),
    );
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
    Map<String, dynamic>? sourceMetadata,
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
    'run': {
      'created_at': '2026-05-08T00:00:00',
    },
    'reason': 'dry_run_risk_approved',
    'quant_buy_score': 74,
    'ai_buy_score': 82,
    'ai_sell_score': 21,
    'confidence': 0.71,
    'final_entry_score': 76,
    'risk_flags': ['dry_run_only', 'fx_pressure'],
    'gating_notes': ['No real KIS order submitted.'],
    'final_best_candidate': {
      'gpt_reason': 'KR scheduler advisory context',
      'indicator_status': 'ok',
      'event_risk': {
        'risk_level': 'medium',
        'event_type': 'earnings',
      },
    },
  };
}

Map<String, dynamic> _autoJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_dry_run_auto',
    'dry_run': true,
    'simulated': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'trigger_source': 'manual_kis_dry_run_auto',
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

Map<String, dynamic> _exitPreflightJson() {
  return {
    'status': 'ok',
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_live_exit_preflight',
    'execution_mode': 'manual_confirm_only',
    'live_auto_enabled': false,
    'auto_buy_enabled': false,
    'auto_sell_enabled': false,
    'real_order_submit_allowed': false,
    'manual_confirm_required': true,
    'checked_at': '2026-05-14T01:00:00Z',
    'run': {
      'run_key': 'kis_live_exit_preflight_abcd1234',
      'run_id': 42,
    },
    'candidate_count': 1,
    'trigger_source': 'manual_kis_live_exit_preflight',
    'preflight': true,
    'simulated': false,
    'live_order_submitted': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'action': 'sell',
    'symbol': '005930',
    'qty': 2,
    'estimated_notional': 141120,
    'cost_basis': 144000,
    'current_value': 141120,
    'unrealized_pl': -2880,
    'unrealized_pl_pct': -0.02,
    'take_profit_threshold_pct': 2.0,
    'stop_loss_threshold_pct': 2.0,
    'exit_trigger_source': 'cost_basis',
    'reason': 'stop_loss_triggered',
    'message':
        'Exit candidate found. Manual confirmation is required before any live sell order.',
    'would_submit_if_enabled': true,
    'blocked_by': [
      'kis_scheduler_allow_real_orders_false',
      'live_scheduler_orders_disabled',
      'preflight_only_no_broker_submit',
    ],
    'risk_flags': [
      'exit_only',
      'preflight_only',
      'no_broker_submit',
      'stop_loss_triggered',
    ],
    'readiness_checks': [
      {'name': 'held_position_exists', 'passed': true},
    ],
    'safety': {
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'scheduler_real_order_enabled': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'manual_confirm_required': true,
    },
    'candidates': [
      {
        'symbol': '005930',
        'side': 'sell',
        'quantity_available': 2,
        'suggested_quantity': 2,
        'current_price': 70560,
        'cost_basis': 144000,
        'current_value': 141120,
        'unrealized_pl': -2880,
        'unrealized_pl_pct': -0.02,
        'trigger': 'stop_loss',
        'trigger_source': 'cost_basis_pl_pct',
        'severity': 'review',
        'action_hint': 'manual_confirm_sell',
        'reason':
            'Position reached stop-loss review threshold. Manual confirmation is required before any live sell order.',
        'risk_flags': [
          'stop_loss_triggered',
          'manual_confirm_required',
          'no_auto_submit',
        ],
        'gating_notes': [
          'manual_confirm_required',
          'no_auto_submit',
        ],
        'submit_ready': false,
        'manual_confirm_required': true,
        'real_order_submit_allowed': false,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      },
    ],
    'result': 'exit_candidate',
  };
}

Map<String, dynamic> _smallProfitHoldExitPreflightJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_live_exit_preflight',
    'trigger_source': 'manual_kis_live_exit_preflight',
    'preflight': true,
    'simulated': false,
    'live_order_submitted': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'action': 'hold',
    'symbol': '091810',
    'qty': 11,
    'estimated_notional': 9867,
    'cost_basis': 9841,
    'current_value': 9867,
    'unrealized_pl': 26,
    'unrealized_pl_pct': 26 / 9841,
    'take_profit_threshold_pct': 2.0,
    'stop_loss_threshold_pct': 2.0,
    'exit_trigger_source': 'cost_basis',
    'reason': 'manual_review_required',
    'message':
        'No held KIS position currently qualifies for live exit automation.',
    'would_submit_if_enabled': false,
    'blocked_by': ['no_exit_condition'],
    'risk_flags': [
      'exit_only',
      'preflight_only',
      'no_broker_submit',
      'manual_review_required',
    ],
    'readiness_checks': [
      {'name': 'held_position_exists', 'passed': true},
    ],
    'result': 'skipped',
  };
}

Map<String, dynamic> _unsafePlExitPreflightJson() {
  return {
    'status': 'ok',
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_live_exit_preflight',
    'execution_mode': 'manual_confirm_only',
    'live_auto_enabled': false,
    'auto_buy_enabled': false,
    'auto_sell_enabled': false,
    'real_order_submit_allowed': false,
    'manual_confirm_required': true,
    'candidate_count': 1,
    'live_order_submitted': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'action': 'sell',
    'symbol': '005930',
    'qty': 1,
    'estimated_notional': 72000,
    'cost_basis': null,
    'current_value': 72000,
    'unrealized_pl': null,
    'unrealized_pl_pct': null,
    'reason': 'risk_exit',
    'message':
        'Exit candidate found. Manual confirmation is required before any live sell order.',
    'would_submit_if_enabled': true,
    'blocked_by': ['preflight_only_no_broker_submit'],
    'risk_flags': [
      'risk_exit',
      'cost_basis_unavailable_current_value_fallback'
    ],
    'safety': {
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'scheduler_real_order_enabled': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'manual_confirm_required': true,
    },
    'candidates': [
      {
        'symbol': '005930',
        'side': 'sell',
        'quantity_available': 1,
        'suggested_quantity': 1,
        'current_price': 72000,
        'cost_basis': null,
        'current_value': 72000,
        'unrealized_pl': null,
        'unrealized_pl_pct': null,
        'trigger': 'manual_review',
        'trigger_source': 'current_value_fallback',
        'severity': 'review',
        'action_hint': 'manual_confirm_sell',
        'reason':
            'Position matched a risk-exit review condition. Manual confirmation is required before any live sell order.',
        'risk_flags': ['risk_exit'],
        'gating_notes': ['manual_confirm_required', 'no_auto_submit'],
        'submit_ready': false,
        'manual_confirm_required': true,
        'real_order_submit_allowed': false,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      },
    ],
    'result': 'exit_candidate',
  };
}

Map<String, dynamic> _noHeldExitPreflightJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_live_exit_preflight',
    'live_order_submitted': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'action': 'hold',
    'symbol': null,
    'qty': null,
    'estimated_notional': null,
    'reason': 'manual_review_required',
    'message': 'No held KIS position to evaluate.',
    'would_submit_if_enabled': false,
    'blocked_by': ['no_held_position'],
    'risk_flags': ['manual_review_required', 'no_held_position'],
    'readiness_checks': [
      {'name': 'held_position_exists', 'passed': false},
    ],
    'result': 'skipped',
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
