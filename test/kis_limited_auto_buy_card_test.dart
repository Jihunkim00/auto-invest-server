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
  test('limited auto buy API methods call readiness endpoints', () async {
    final paths = <String>[];
    final client = ApiClient(
      client: MockClient((request) async {
        paths.add('${request.method} ${request.url.path}');
        return http.Response(jsonEncode(_limitedAutoBuyJson()), 200);
      }),
    );

    await client.fetchKisLimitedAutoBuyStatus();
    await client.runKisLimitedAutoBuyPreflightOnce();
    final result = await client.runKisLimitedAutoBuyOnce();

    expect(paths, [
      'GET /kis/limited-auto-buy/status',
      'POST /kis/limited-auto-buy/preflight-once',
      'POST /kis/limited-auto-buy/run-once',
    ]);
    expect(result.mode, 'kis_limited_auto_buy_run');
    expect(paths.join('\n'), isNot(contains('/kis/orders/manual-submit')));
    expect(paths.join('\n'), isNot(contains('/kis/orders/validate')));
  });

  testWidgets('limited auto buy card renders disabled readiness-only state',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 4400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeLimitedAutoBuyApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_limited_auto_buy_card'));
    expect(card, findsOneWidget);
    for (final label in [
      'BUY READINESS ONLY',
      'AUTO BUY DISABLED',
      'NO BROKER SUBMIT',
      'SCHEDULER REAL ORDERS DISABLED',
      'DEFAULT OFF',
      'GUARDED FUTURE BUY',
      'READINESS / PREFLIGHT',
    ]) {
      expect(find.descendant(of: card, matching: find.text(label)),
          findsOneWidget);
    }
    expect(find.text('Enable Auto Buy'), findsNothing);
    expect(find.text('Submit Buy'), findsNothing);
    expect(find.text('Enable Scheduler Real Orders'), findsNothing);

    final refreshButton = find.descendant(
      of: card,
      matching: find.text('Refresh Buy Status'),
    );
    await tester.ensureVisible(refreshButton);
    await tester.tap(refreshButton);
    await tester.pumpAndSettle();

    expect(api.statusCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.text('auto_buy_execution_disabled'), findsWidgets);

    controller.dispose();
  });

  testWidgets('preflight result renders candidate and no-order reason',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 5200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeLimitedAutoBuyApi(
      result: KisLimitedAutoBuy.fromJson(
        _limitedAutoBuyJson(mode: 'kis_limited_auto_buy_preflight'),
      ),
    );
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    final card = find.byKey(const Key('kis_limited_auto_buy_card'));
    final preflightButton = find.descendant(
      of: card,
      matching: find.text('Run Buy Preflight'),
    );
    await tester.ensureVisible(preflightButton);
    await tester.tap(preflightButton);
    await tester.pumpAndSettle();

    expect(api.preflightCalls, 1);
    expect(find.text('005930 · Samsung Electronics'), findsWidgets);
    expect(find.text('BUY READY'), findsWidgets);
    expect(find.text('KRW 288,000'), findsWidgets);
    expect(find.textContaining('82.5 / 75'), findsWidgets);
    expect(
        find.text('why no order: auto_buy_execution_disabled'), findsWidgets);
    expect(find.text('Developer Raw Payload'), findsOneWidget);
    expect(
        find.textContaining('"source": "kis_limited_auto_buy"'), findsNothing);

    controller.dispose();
  });

  testWidgets('run-once shows buy ready but auto buy disabled no broker submit',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 5200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeLimitedAutoBuyApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    final runButton = find.descendant(
      of: find.byKey(const Key('kis_limited_auto_buy_card')),
      matching: find.text('Run Limited Buy Once'),
    );
    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(find.text('BUY READY'), findsWidgets);
    expect(find.text('auto_buy_enabled=false'), findsOneWidget);
    expect(find.text('BROKER_SUBMIT_CALLED'), findsWidgets);
    expect(find.text('false'), findsWidgets);
    expect(find.textContaining('UNEXPECTED LIVE BUY SUBMITTED'), findsNothing);

    controller.dispose();
  });

  testWidgets('weak candidate shows score below threshold', (tester) async {
    tester.view.physicalSize = const Size(1200, 5200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeLimitedAutoBuyApi(
      result: KisLimitedAutoBuy.fromJson(_limitedAutoBuyJson(weak: true)),
    );
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    final runButton = find.descendant(
      of: find.byKey(const Key('kis_limited_auto_buy_card')),
      matching: find.text('Run Limited Buy Once'),
    );
    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(find.text('score_threshold_not_met'), findsWidgets);
    expect(find.textContaining('60 / 75'), findsWidgets);

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
  int statusCalls = 0;
  int preflightCalls = 0;
  int runCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisLimitedAutoBuy> fetchKisLimitedAutoBuyStatus(
      {int? gateLevel}) async {
    statusCalls += 1;
    return KisLimitedAutoBuy.fromJson(
      _limitedAutoBuyJson(mode: 'kis_limited_auto_buy_status', blocked: true),
    );
  }

  @override
  Future<KisLimitedAutoBuy> runKisLimitedAutoBuyPreflightOnce({
    int? gateLevel,
  }) async {
    preflightCalls += 1;
    return result;
  }

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

Map<String, dynamic> _limitedAutoBuyJson({
  String mode = 'kis_limited_auto_buy_run',
  bool blocked = false,
  bool weak = false,
}) {
  final candidate = _candidate(weak: weak);
  final blockReasons = weak
      ? ['score_threshold_not_met', 'auto_buy_execution_disabled']
      : ['auto_buy_execution_disabled'];
  return {
    'status': 'ok',
    'mode': mode,
    'source': 'kis_limited_auto_buy',
    'source_type': 'buy_readiness_only',
    'result': blocked
        ? 'blocked'
        : weak
            ? 'blocked'
            : 'readiness_only',
    'action': weak || blocked ? 'hold' : 'buy_ready',
    'reason': blocked
        ? 'auto_buy_execution_disabled'
        : weak
            ? 'score_threshold_not_met'
            : 'buy_readiness_only',
    'primary_block_reason': blocked
        ? 'auto_buy_execution_disabled'
        : weak
            ? 'score_threshold_not_met'
            : 'auto_buy_execution_disabled',
    'symbol': blocked ? null : '005930',
    'quantity': blocked ? null : 4,
    'estimated_notional': blocked ? null : 288000,
    'final_buy_score': blocked
        ? null
        : weak
            ? 60.0
            : 82.5,
    'final_sell_score': blocked ? null : 12.0,
    'confidence': blocked ? null : 0.76,
    'required_buy_score': blocked ? null : 75.0,
    'buy_sell_spread': blocked
        ? null
        : weak
            ? 48.0
            : 70.5,
    'live_auto_buy_enabled': false,
    'limited_auto_buy_enabled': false,
    'buy_readiness_enabled': true,
    'dry_run': true,
    'kill_switch': false,
    'kis_real_order_enabled': true,
    'market_open': true,
    'entry_allowed_now': true,
    'no_new_entry_after': '14:50',
    'cash_available': 3000000,
    'daily_buy_count': 0,
    'daily_buy_limit': 1,
    'max_notional_pct': 0.03,
    'real_order_submit_allowed': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'validation_called': false,
    'auto_buy_enabled': false,
    'scheduler_real_orders_enabled': false,
    'block_reasons': blockReasons,
    'blocked_by': blockReasons,
    'candidates': blocked ? [] : [candidate],
    'final_candidate': blocked ? null : candidate,
    'checks': {
      'kis_limited_auto_buy_enabled': false,
      'kis_limited_auto_buy_readiness_enabled': true,
    },
    'safety': {
      'buy_readiness_only': true,
      'auto_buy_execution_enabled': false,
      'real_order_submit_allowed': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'validation_called': false,
    },
    'audit_metadata': {'source': 'kis_limited_auto_buy'},
  };
}

Map<String, dynamic> _candidate({bool weak = false}) {
  final buyScore = weak ? 60.0 : 82.5;
  return {
    'symbol': '005930',
    'company_name': 'Samsung Electronics',
    'status': weak ? 'WATCH' : 'BUY READY',
    'current_price': 72000,
    'available_cash': 3000000,
    'estimated_notional': 288000,
    'suggested_quantity': 4,
    'max_notional_pct': 0.03,
    'final_buy_score': buyScore,
    'final_sell_score': 12.0,
    'quant_buy_score': weak ? 58.0 : 78.0,
    'quant_sell_score': 10.0,
    'gpt_buy_score': 65.0,
    'confidence': 0.76,
    'required_buy_score': 75.0,
    'effective_min_entry_score': 75.0,
    'buy_sell_spread': weak ? 48.0 : 70.5,
    'indicator_status': 'ready',
    'indicator_bar_count': 120,
    'technical_snapshot': {
      'EMA20': 70500,
      'EMA50': 69000,
      'VWAP': 71200,
      'RSI': 57.5,
      'ATR': 1200,
      'volume_ratio': 1.3,
      'recent_return': 0.018,
      'momentum': 0.021,
      'price_position': 'above_ema20',
    },
    'entry_ready': !weak,
    'trade_allowed': false,
    'buy_readiness_only': true,
    'buy_actionable': false,
    'duplicate_position': false,
    'duplicate_open_buy_order': false,
    'cash_sufficient': true,
    'market_session_allowed': true,
    'no_new_entry_after_blocked': false,
    'daily_buy_limit_remaining': 1,
    'risk_flags': weak ? ['score_threshold_not_met'] : [],
    'gating_notes': ['auto_buy_disabled'],
    'block_reasons': weak ? ['score_threshold_not_met'] : [],
    'gpt_reason': 'Quant-first buy setup is constructive.',
  };
}
