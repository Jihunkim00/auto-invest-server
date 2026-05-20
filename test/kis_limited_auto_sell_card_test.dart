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
            of: limitedAutoSellCard, matching: find.text('READINESS ONLY')),
        findsWidgets);
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
        matching: find.text('TAKE-PROFIT DISABLED'),
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
        matching: find.text('DEFAULT OFF'),
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
    expect(find.text('KRW -4,000 / -4.00%'), findsWidgets);
    expect(find.text('2.00%'), findsWidgets);
    expect(find.text('TAKE-PROFIT DISABLED'), findsWidgets);
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
    'safety': {
      'max_orders_per_day': 1,
      'take_profit_disabled': true,
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
      'status': 'SELL_READY',
      'reason': 'Stop-loss threshold reached.',
    },
    'raw_marker': 'developer only',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
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
    'block_reasons': ['preflight_read_only_no_submit'],
    'safety': {
      'max_orders_per_day': 1,
      'stop_loss_only': true,
      'take_profit_auto_sell_enabled': false,
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
