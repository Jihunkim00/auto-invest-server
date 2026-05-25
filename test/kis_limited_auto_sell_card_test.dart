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
  test('limited auto sell API calls status preflight and run endpoints',
      () async {
    late http.Request captured;
    final paths = <String>[];
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        paths.add(request.url.path);
        if (request.url.path == '/kis/limited-auto-sell/status') {
          return http.Response(jsonEncode(_limitedAutoSellStatusJson()), 200);
        }
        if (request.url.path == '/kis/limited-auto-sell/preflight-once') {
          return http.Response(
              jsonEncode(_limitedAutoSellPreflightJson()), 200);
        }
        return http.Response(jsonEncode(_limitedAutoSellRunJson()), 200);
      }),
    );

    final status = await client.fetchKisLimitedAutoSellStatus();
    final preflight = await client.runKisLimitedAutoSellPreflightOnce();
    final result = await client.runKisLimitedAutoSellOnce();

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/limited-auto-sell/run-once');
    expect(captured.body, '{}');
    expect(paths, [
      '/kis/limited-auto-sell/status',
      '/kis/limited-auto-sell/preflight-once',
      '/kis/limited-auto-sell/run-once',
    ]);
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/validate')));
    expect(status.mode, 'kis_limited_auto_stop_loss_status');
    expect(preflight.mode, 'kis_limited_auto_stop_loss_preflight');
    expect(result.mode, 'kis_limited_auto_stop_loss_run');
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
        of: limitedAutoSellCard,
        matching: find.text('STOP-LOSS EXECUTION'),
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
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('TAKE-PROFIT GUARDED EXECUTION'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('TAKE-PROFIT DEFAULT OFF'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('AUTO BUY DISABLED'),
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
        matching: find.text('NO BROKER SUBMIT'),
      ),
      findsWidgets,
    );
    expect(
        find.descendant(
          of: limitedAutoSellCard,
          matching: find.text('Refresh Status'),
        ),
        findsOneWidget);
    expect(
        find.descendant(
          of: limitedAutoSellCard,
          matching: find.text('Run Stop-Loss Preflight'),
        ),
        findsOneWidget);
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
    expect(api.statusCalls, 0);
    expect(api.preflightCalls, 0);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.text('dry_run_true'), findsWidgets);
    expect(find.text('blocked'), findsWidgets);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
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

  testWidgets('preflight result renders stop-loss candidate and raw collapsed',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(
      _FakeLimitedAutoSellApi(
        preflightResult:
            KisLimitedAutoSell.fromJson(_limitedAutoSellPreflightJson()),
      ),
    );

    await tester.pumpWidget(_wrap(controller));
    final limitedAutoSellCard =
        find.byKey(const Key('kis_limited_auto_sell_card'));
    final preflightButton = find.descendant(
      of: limitedAutoSellCard,
      matching: find.text('Run Stop-Loss Preflight'),
    );
    await tester.ensureVisible(preflightButton);
    await tester.tap(preflightButton);
    await tester.pumpAndSettle();

    expect(find.textContaining('LIVE SELL SUBMITTED'), findsNothing);
    expect(find.textContaining('005930'), findsWidgets);
    expect(find.textContaining('Samsung Electronics'), findsWidgets);
    expect(find.text('SELL READY'), findsWidgets);
    expect(find.text('KRW 96,000'), findsWidgets);
    expect(find.text('KRW 100,000'), findsWidgets);
    expect(find.text('KRW -4,000 / -4.00%'), findsWidgets);
    expect(find.text('2.00%'), findsWidgets);
    expect(find.textContaining('preflight_read_only_no_submit'), findsWidgets);
    expect(find.textContaining('stop_loss=true'), findsWidgets);
    expect(find.text('TAKE-PROFIT GUARDED EXECUTION'), findsWidgets);
    expect(find.text('Developer Raw Payload'), findsOneWidget);
    expect(find.textContaining('"raw_marker"'), findsNothing);

    controller.dispose();
  });

  testWidgets('refresh status shows default blocked readiness', (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeLimitedAutoSellApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    final limitedAutoSellCard =
        find.byKey(const Key('kis_limited_auto_sell_card'));
    final refreshButton = find.descendant(
      of: limitedAutoSellCard,
      matching: find.text('Refresh Status'),
    );
    await tester.ensureVisible(refreshButton);
    await tester.tap(refreshButton);
    await tester.pumpAndSettle();

    expect(api.statusCalls, 1);
    expect(find.text('dry_run_true'), findsWidgets);
    expect(find.textContaining('kis_live_auto_sell_disabled'), findsWidgets);
    expect(find.text('TAKE_PROFIT_EXECUTION_ENABLED'), findsOneWidget);
    expect(find.text('false'), findsWidgets);

    // Do not require raw payload keys to be visible in the operator UI.
    expect(find.text('supported triggers'), findsNothing);

    // Assert the operator-facing trigger information instead.
    expect(find.textContaining('STOP-LOSS'), findsWidgets);
    expect(find.textContaining('TAKE-PROFIT'), findsWidgets);
    expect(find.textContaining('GUARDED'), findsWidgets);
    expect(find.textContaining('READINESS'), findsWidgets);

    controller.dispose();
  });

  testWidgets('preflight take-profit candidate renders readiness only',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(
      _FakeLimitedAutoSellApi(
        preflightResult: KisLimitedAutoSell.fromJson(
          _limitedAutoSellTakeProfitPreflightJson(),
        ),
      ),
    );

    await tester.pumpWidget(_wrap(controller));
    final limitedAutoSellCard =
        find.byKey(const Key('kis_limited_auto_sell_card'));
    final preflightButton = find.descendant(
      of: limitedAutoSellCard,
      matching: find.text('Run Stop-Loss Preflight'),
    );
    await tester.ensureVisible(preflightButton);
    await tester.tap(preflightButton);
    await tester.pumpAndSettle();

    expect(find.text('TAKE-PROFIT READY'), findsWidgets);
    expect(find.text('TAKE PROFIT READY'), findsWidgets);
    expect(find.textContaining('Readiness only'), findsWidgets);
    expect(find.textContaining('Take-profit execution disabled'), findsWidgets);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.textContaining('take_profit_execution_disabled'), findsWidgets);
    expect(find.textContaining('"raw_marker"'), findsNothing);

    controller.dispose();
  });

  testWidgets('run once take-profit-only payload shows blocked no submit',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeLimitedAutoSellApi(
      runResult:
          KisLimitedAutoSell.fromJson(_limitedAutoSellTakeProfitRunJson()),
    );
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    final limitedAutoSellCard =
        find.byKey(const Key('kis_limited_auto_sell_card'));
    final runButton = find.descendant(
      of: limitedAutoSellCard,
      matching: find.text('Run Limited Auto Sell Once'),
    );
    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(find.text('blocked'), findsWidgets);
    expect(find.textContaining('take_profit_auto_sell_disabled'), findsWidgets);
    expect(find.text('Take-profit auto sell disabled'), findsWidgets);
    expect(find.text('TAKE-PROFIT READY'), findsWidgets);
    expect(find.text('REAL_ORDER_SUBMITTED'), findsOneWidget);
    expect(find.text('false'), findsWidgets);
    expect(find.text('BROKER_SUBMIT_CALLED'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.textContaining('LIVE SELL SUBMITTED'), findsNothing);

    controller.dispose();
  });

  testWidgets('submitted result shows broker submit and KIS order ids',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeLimitedAutoSellApi(
      runResult: KisLimitedAutoSell.fromJson(_limitedAutoSellSubmittedJson()),
    );
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    final limitedAutoSellCard =
        find.byKey(const Key('kis_limited_auto_sell_card'));
    final runButton = find.descendant(
      of: limitedAutoSellCard,
      matching: find.text('Run Limited Auto Sell Once'),
    );
    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(find.textContaining('LIVE SELL SUBMITTED'), findsOneWidget);
    expect(find.text('submitted'), findsWidgets);
    expect(find.text('BROKER SUBMIT CALLED'), findsWidgets);
    final sellCard = find.byKey(const Key('kis_limited_auto_sell_card'));

    expect(
      find.descendant(
        of: sellCard,
        matching: find.text('ORDER ID'),
      ),
      findsOneWidget,
    );
    expect(find.text('77'), findsOneWidget);
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('KIS ODNO'),
      ),
      findsOneWidget,
    );
    expect(find.text('ODNO777'), findsWidgets);
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('NO BROKER SUBMIT'),
      ),
      findsNothing,
    );
    expect(find.text('passed'), findsWidgets);

    controller.dispose();
  });

  testWidgets('submitted take-profit result shows trigger and KIS order ids',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeLimitedAutoSellApi(
      runResult: KisLimitedAutoSell.fromJson(
          _limitedAutoSellTakeProfitSubmittedJson()),
    );
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    final limitedAutoSellCard =
        find.byKey(const Key('kis_limited_auto_sell_card'));
    final runButton = find.descendant(
      of: limitedAutoSellCard,
      matching: find.text('Run Limited Auto Sell Once'),
    );
    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(find.textContaining('LIVE SELL SUBMITTED'), findsOneWidget);
    expect(find.text('submitted'), findsWidgets);
    expect(find.text('take_profit'), findsWidgets);
    expect(find.text('BROKER SUBMIT CALLED'), findsWidgets);
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('ORDER ID'),
      ),
      findsOneWidget,
    );
    expect(find.text('88'), findsOneWidget);
    expect(
      find.descendant(
        of: limitedAutoSellCard,
        matching: find.text('KIS ODNO'),
      ),
      findsOneWidget,
    );
    expect(find.text('TPODNO888'), findsWidgets);

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
          builder: (context, _) => TestLabSection(
              controller: controller, advancedInitiallyExpanded: true),
        ),
      ),
    ),
  );
}

class _FakeLimitedAutoSellApi extends ApiClient {
  _FakeLimitedAutoSellApi({
    KisLimitedAutoSell? statusResult,
    KisLimitedAutoSell? preflightResult,
    KisLimitedAutoSell? runResult,
  })  : statusResult = statusResult ??
            KisLimitedAutoSell.fromJson(_limitedAutoSellStatusJson()),
        preflightResult = preflightResult ??
            KisLimitedAutoSell.fromJson(_limitedAutoSellPreflightJson()),
        runResult =
            runResult ?? KisLimitedAutoSell.fromJson(_limitedAutoSellRunJson());

  KisLimitedAutoSell statusResult;
  KisLimitedAutoSell preflightResult;
  KisLimitedAutoSell runResult;
  int statusCalls = 0;
  int preflightCalls = 0;
  int runCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisLimitedAutoSell> fetchKisLimitedAutoSellStatus() async {
    statusCalls += 1;
    return statusResult;
  }

  @override
  Future<KisLimitedAutoSell> runKisLimitedAutoSellPreflightOnce() async {
    preflightCalls += 1;
    return preflightResult;
  }

  @override
  Future<KisLimitedAutoSell> runKisLimitedAutoSellOnce() async {
    runCalls += 1;
    return runResult;
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

Map<String, dynamic> _limitedAutoSellStatusJson() {
  return {
    'status': 'ok',
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_limited_auto_stop_loss_status',
    'result': 'blocked',
    'action': 'hold',
    'reason': 'dry_run_true',
    'primary_block_reason': 'dry_run_true',
    'live_auto_sell_enabled': false,
    'stop_loss_auto_sell_enabled': false,
    'take_profit_auto_sell_enabled': false,
    'scheduler_real_orders_enabled': false,
    'dry_run': true,
    'kill_switch': false,
    'kis_real_order_enabled': false,
    'market_open': true,
    'sell_session_allowed': true,
    'auto_order_ready': false,
    'real_order_submit_allowed': false,
    'stop_loss_execution_enabled': false,
    'take_profit_readiness_enabled': true,
    'take_profit_execution_enabled': false,
    'take_profit_non_actionable': true,
    'take_profit_actionable': false,
    'take_profit_readiness_only': false,
    'take_profit_execution_disabled': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'auto_buy_enabled': false,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'block_reasons': [
      'dry_run_true',
      'kis_live_auto_sell_disabled',
      'stop_loss_auto_sell_disabled',
    ],
    'daily_limit_remaining': 1,
    'daily_limit': {
      'max_orders_per_day': 1,
      'submitted_count_today': 0,
      'daily_limit_remaining': 1,
      'symbol_already_auto_sold_today': false,
      'daily_limit_reached': false,
    },
    'duplicate_order_check': {
      'duplicate_open_sell_order': false,
      'latest_related_sell_order': null,
    },
    'validation_status': 'not_called',
    'readiness_labels': [
      'STOP-LOSS EXECUTION',
      'TAKE-PROFIT GUARDED EXECUTION',
      'TAKE-PROFIT DEFAULT OFF',
      'GUARDED EXECUTION',
      'AUTO BUY DISABLED',
      'SCHEDULER REAL ORDERS DISABLED',
      'TAKE-PROFIT AUTO SELL DISABLED',
      'NO BROKER SUBMIT',
    ],
    'safety': {
      'max_orders_per_day': 1,
      'take_profit_disabled': true,
      'take_profit_readiness_enabled': true,
      'take_profit_execution_enabled': false,
      'take_profit_non_actionable': true,
      'auto_buy_disabled': true,
      'scheduler_real_orders_enabled': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
    'checks': {
      'dry_run': true,
      'kis_live_auto_sell_enabled': false,
      'kis_limited_auto_stop_loss_enabled': false,
    },
    'supported_triggers': {
      'stop_loss': {'mode': 'guarded_execution'},
      'take_profit': {'mode': 'readiness_only'},
    },
  };
}

Map<String, dynamic> _limitedAutoSellRunJson() {
  final payload = _limitedAutoSellStatusJson();
  payload['mode'] = 'kis_limited_auto_stop_loss_run';
  return payload;
}

Map<String, dynamic> _limitedAutoSellPreflightJson() {
  return {
    'status': 'ok',
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_limited_auto_stop_loss_preflight',
    'source': 'kis_limited_auto_stop_loss',
    'source_type': 'limited_auto_sell_preflight',
    'result': 'preview_only',
    'action': 'sell_ready',
    'reason': 'stop_loss_candidate_ready_read_only',
    'primary_block_reason': 'preflight_read_only_no_submit',
    'candidate_count': 1,
    'candidates': [
      {
        'symbol': '005930',
        'company_name': 'Samsung Electronics',
        'quantity': 1,
        'current_price': 96000,
        'average_price': 100000,
        'cost_basis': 100000,
        'current_value': 96000,
        'unrealized_pl': -4000,
        'unrealized_pl_pct': -0.04,
        'stop_loss_threshold_pct': 2.0,
        'take_profit_threshold_pct': 2.0,
        'stop_loss_triggered': true,
        'take_profit_triggered': false,
        'take_profit_readiness_only': false,
        'take_profit_actionable': false,
        'take_profit_execution_disabled': false,
        'weak_trend_triggered': false,
        'sell_pressure_triggered': false,
        'status': 'SELL_READY',
        'reason': 'Stop-loss threshold reached.',
        'block_reasons': const [],
        'risk_flags': ['stop_loss_triggered'],
        'gating_notes': ['preflight_read_only'],
      }
    ],
    'final_candidate': {
      'symbol': '005930',
      'company_name': 'Samsung Electronics',
      'quantity': 1,
      'current_price': 96000,
      'average_price': 100000,
      'cost_basis': 100000,
      'current_value': 96000,
      'unrealized_pl': -4000,
      'unrealized_pl_pct': -0.04,
      'stop_loss_threshold_pct': 2.0,
      'take_profit_threshold_pct': 2.0,
      'stop_loss_triggered': true,
      'take_profit_triggered': false,
      'take_profit_readiness_only': false,
      'take_profit_actionable': false,
      'take_profit_execution_disabled': false,
      'status': 'SELL_READY',
      'reason': 'Stop-loss threshold reached.',
    },
    'raw_marker': 'developer only',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'stop_loss_triggered': true,
    'take_profit_triggered': false,
    'weak_trend_triggered': false,
    'sell_pressure_triggered': false,
    'auto_buy_enabled': false,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'live_auto_sell_enabled': false,
    'stop_loss_auto_sell_enabled': false,
    'take_profit_auto_sell_enabled': false,
    'scheduler_real_orders_enabled': false,
    'dry_run': true,
    'kill_switch': false,
    'kis_real_order_enabled': true,
    'market_open': true,
    'sell_session_allowed': true,
    'auto_order_ready': false,
    'real_order_submit_allowed': false,
    'stop_loss_execution_enabled': false,
    'take_profit_readiness_enabled': true,
    'take_profit_execution_enabled': false,
    'take_profit_non_actionable': true,
    'take_profit_actionable': false,
    'take_profit_readiness_only': false,
    'take_profit_execution_disabled': false,
    'block_reasons': ['preflight_read_only_no_submit'],
    'daily_limit_remaining': 1,
    'daily_limit': {
      'max_orders_per_day': 1,
      'submitted_count_today': 0,
      'daily_limit_remaining': 1,
      'symbol_already_auto_sold_today': false,
      'daily_limit_reached': false,
    },
    'duplicate_order_check': {
      'duplicate_open_sell_order': false,
      'latest_related_sell_order': null,
    },
    'validation_status': 'not_called_read_only',
    'readiness_labels': [
      'STOP-LOSS EXECUTION',
      'TAKE-PROFIT GUARDED EXECUTION',
      'TAKE-PROFIT DEFAULT OFF',
      'GUARDED EXECUTION',
      'AUTO BUY DISABLED',
      'SCHEDULER REAL ORDERS DISABLED',
      'TAKE-PROFIT AUTO SELL DISABLED',
      'NO BROKER SUBMIT',
      'READ-ONLY',
    ],
    'safety': {
      'max_orders_per_day': 1,
      'stop_loss_only': true,
      'take_profit_auto_sell_enabled': false,
      'take_profit_readiness_enabled': true,
      'take_profit_execution_enabled': false,
      'take_profit_non_actionable': true,
      'auto_buy_enabled': false,
      'scheduler_real_orders_enabled': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
    'audit_metadata': {
      'source': 'kis_limited_auto_stop_loss',
      'source_type': 'limited_auto_sell_preflight',
    },
  };
}

Map<String, dynamic> _limitedAutoSellSubmittedJson() {
  final payload = _limitedAutoSellPreflightJson();
  payload['mode'] = 'kis_limited_auto_stop_loss_run';
  payload['source_type'] = 'guarded_stop_loss_auto_sell';
  payload['trigger_source'] = 'limited_auto_sell_run_once';
  payload['result'] = 'submitted';
  payload['action'] = 'sell';
  payload['reason'] = 'stop_loss_auto_sell_submitted';
  payload['primary_block_reason'] = null;
  payload['live_auto_sell_enabled'] = true;
  payload['stop_loss_auto_sell_enabled'] = true;
  payload['dry_run'] = false;
  payload['kis_real_order_enabled'] = true;
  payload['auto_order_ready'] = true;
  payload['real_order_submit_allowed'] = true;
  payload['stop_loss_execution_enabled'] = true;
  payload['take_profit_readiness_enabled'] = true;
  payload['take_profit_execution_enabled'] = false;
  payload['take_profit_non_actionable'] = true;
  payload['take_profit_actionable'] = false;
  payload['take_profit_readiness_only'] = false;
  payload['take_profit_execution_disabled'] = false;
  payload['real_order_submitted'] = true;
  payload['broker_submit_called'] = true;
  payload['manual_submit_called'] = true;
  payload['order_id'] = 77;
  payload['order_log_id'] = 77;
  payload['broker_order_id'] = 'BRK777';
  payload['kis_odno'] = 'ODNO777';
  payload['block_reasons'] = const [];
  payload['validation_status'] = 'passed';
  payload['readiness_labels'] = [
    'STOP-LOSS EXECUTION',
    'TAKE-PROFIT GUARDED EXECUTION',
    'TAKE-PROFIT DEFAULT OFF',
    'GUARDED EXECUTION',
    'AUTO BUY DISABLED',
    'SCHEDULER REAL ORDERS DISABLED',
    'TAKE-PROFIT AUTO SELL DISABLED',
    'BROKER SUBMIT CALLED',
  ];
  payload['daily_limit'] = {
    'max_orders_per_day': 1,
    'submitted_count_today': 0,
    'daily_limit_remaining': 1,
    'symbol_already_auto_sold_today': false,
    'daily_limit_reached': false,
  };
  payload['safety'] = {
    ...Map<String, dynamic>.from(payload['safety'] as Map),
    'read_only': false,
    'guarded_execution': true,
    'real_order_submitted': true,
    'broker_submit_called': true,
    'manual_submit_called': true,
    'no_broker_submit': false,
  };
  return payload;
}

Map<String, dynamic> _limitedAutoSellTakeProfitPreflightJson() {
  final payload = _limitedAutoSellPreflightJson();
  final candidate = {
    'symbol': '005930',
    'company_name': 'Samsung Electronics',
    'quantity': 1,
    'current_price': 103000,
    'average_price': 100000,
    'cost_basis': 100000,
    'current_value': 103000,
    'unrealized_pl': 3000,
    'unrealized_pl_pct': 0.03,
    'stop_loss_threshold_pct': 2.0,
    'take_profit_threshold_pct': 3.0,
    'stop_loss_triggered': false,
    'take_profit_triggered': true,
    'take_profit_readiness_only': true,
    'take_profit_actionable': false,
    'take_profit_execution_disabled': true,
    'weak_trend_triggered': false,
    'sell_pressure_triggered': false,
    'status': 'TAKE_PROFIT_READY',
    'reason': 'Take-profit readiness only.',
    'block_reasons': [
      'take_profit_execution_disabled',
      'take_profit_readiness_only',
    ],
    'risk_flags': ['take_profit_triggered'],
    'gating_notes': ['take_profit_readiness_only'],
  };
  payload['source'] = 'kis_limited_auto_take_profit';
  payload['source_type'] = 'take_profit_readiness_only';
  payload['result'] = 'preview_only';
  payload['action'] = 'review_sell';
  payload['reason'] = 'take_profit_readiness_only';
  payload['primary_block_reason'] = 'preflight_read_only_no_submit';
  payload['candidates'] = [candidate];
  payload['final_candidate'] = candidate;
  payload['current_price'] = 103000;
  payload['current_value'] = 103000;
  payload['cost_basis'] = 100000;
  payload['unrealized_pl'] = 3000;
  payload['unrealized_pl_pct'] = 0.03;
  payload['stop_loss_triggered'] = false;
  payload['take_profit_triggered'] = true;
  payload['take_profit_readiness_only'] = true;
  payload['take_profit_actionable'] = false;
  payload['take_profit_execution_disabled'] = true;
  payload['block_reasons'] = [
    'preflight_read_only_no_submit',
    'take_profit_execution_disabled',
    'take_profit_readiness_only',
  ];
  payload['audit_metadata'] = {
    'source': 'kis_limited_auto_take_profit',
    'source_type': 'take_profit_readiness_only',
  };
  return payload;
}

Map<String, dynamic> _limitedAutoSellTakeProfitRunJson() {
  final payload = _limitedAutoSellTakeProfitPreflightJson();
  payload['mode'] = 'kis_limited_auto_take_profit_run';
  payload['source_type'] = 'guarded_take_profit_auto_sell';
  payload['result'] = 'blocked';
  payload['action'] = 'blocked_sell';
  payload['reason'] = 'take_profit_auto_sell_disabled';
  payload['primary_block_reason'] = 'take_profit_auto_sell_disabled';
  payload['block_reasons'] = [
    'take_profit_auto_sell_disabled',
    'take_profit_readiness_only',
  ];
  payload['validation_status'] = 'not_called';
  return payload;
}

Map<String, dynamic> _limitedAutoSellTakeProfitSubmittedJson() {
  final payload = _limitedAutoSellTakeProfitPreflightJson();
  final candidate =
      Map<String, dynamic>.from(payload['final_candidate'] as Map);
  candidate['take_profit_actionable'] = true;
  candidate['take_profit_execution_disabled'] = false;
  candidate['take_profit_readiness_only'] = false;
  candidate['block_reasons'] = const [];
  payload['mode'] = 'kis_limited_auto_take_profit_run';
  payload['source_type'] = 'guarded_take_profit_auto_sell';
  payload['trigger_source'] = 'limited_auto_sell_run_once';
  payload['result'] = 'submitted';
  payload['action'] = 'sell';
  payload['reason'] = 'take_profit_auto_sell_submitted';
  payload['primary_block_reason'] = null;
  payload['trigger'] = 'take_profit';
  payload['exit_trigger'] = 'take_profit';
  payload['final_candidate'] = candidate;
  payload['candidates'] = [candidate];
  payload['live_auto_sell_enabled'] = true;
  payload['stop_loss_auto_sell_enabled'] = true;
  payload['take_profit_auto_sell_enabled'] = true;
  payload['dry_run'] = false;
  payload['kis_real_order_enabled'] = true;
  payload['auto_order_ready'] = true;
  payload['real_order_submit_allowed'] = true;
  payload['stop_loss_execution_enabled'] = true;
  payload['take_profit_execution_enabled'] = true;
  payload['take_profit_non_actionable'] = false;
  payload['take_profit_actionable'] = true;
  payload['take_profit_readiness_only'] = false;
  payload['take_profit_execution_disabled'] = false;
  payload['real_order_submitted'] = true;
  payload['broker_submit_called'] = true;
  payload['manual_submit_called'] = true;
  payload['order_id'] = 88;
  payload['order_log_id'] = 88;
  payload['broker_order_id'] = 'TPBRK888';
  payload['kis_odno'] = 'TPODNO888';
  payload['block_reasons'] = const [];
  payload['validation_status'] = 'passed';
  payload['readiness_labels'] = [
    'STOP-LOSS EXECUTION',
    'TAKE-PROFIT GUARDED EXECUTION',
    'TAKE-PROFIT DEFAULT OFF',
    'GUARDED EXECUTION',
    'AUTO BUY DISABLED',
    'SCHEDULER REAL ORDERS DISABLED',
    'TAKE-PROFIT AUTO SELL ENABLED',
    'BROKER SUBMIT CALLED',
  ];
  payload['supported_triggers'] = {
    'stop_loss': {'mode': 'guarded_execution'},
    'take_profit': {'mode': 'guarded_execution'},
  };
  payload['safety'] = {
    ...Map<String, dynamic>.from(payload['safety'] as Map),
    'read_only': false,
    'guarded_execution': true,
    'take_profit_auto_sell_enabled': true,
    'take_profit_execution_enabled': true,
    'take_profit_non_actionable': false,
    'real_order_submitted': true,
    'broker_submit_called': true,
    'manual_submit_called': true,
    'no_broker_submit': false,
  };
  return payload;
}
