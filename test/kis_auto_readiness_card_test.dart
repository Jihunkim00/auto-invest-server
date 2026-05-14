import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_auto_readiness.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('runKisAutoPreflightOnce posts empty readiness preflight payload',
      () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_readinessJson(preflight: true)), 200);
      }),
    );

    final result = await client.runKisAutoPreflightOnce();

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/auto/preflight-once');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.body, '{}');
    expect(captured.body, isNot(contains('symbol')));
    expect(captured.body, isNot(contains('qty')));
    expect(captured.body, isNot(contains('side')));
    expect(result.realOrderSubmitAllowed, isFalse);
  });

  test('fetchKisAutoReadiness uses readiness endpoint', () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_readinessJson()), 200);
      }),
    );

    final result = await client.fetchKisAutoReadiness();

    expect(captured.method, 'GET');
    expect(captured.url.path, '/kis/auto/readiness');
    expect(result.autoOrderReady, isFalse);
    expect(result.reason, 'live_auto_disabled_by_default');
  });

  testWidgets('KIS live auto readiness card shows blocked safety labels',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 1800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _readinessController(_FakeReadinessApiClient());

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('KIS Live Auto Readiness'), findsOneWidget);
    expect(find.text('READINESS ONLY'), findsOneWidget);
    expect(find.text('LIVE AUTO DISABLED'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('MANUAL CONFIRM REQUIRED'), findsOneWidget);
    expect(find.text('real_order_submit_allowed=false'), findsOneWidget);
    expect(find.text('auto_order_ready=false'), findsOneWidget);
    expect(find.text('live_auto_disabled_by_default'), findsWidgets);
    expect(find.text('real_order_submitted=false'), findsOneWidget);
    expect(find.text('broker_submit_called=false'), findsOneWidget);
    expect(find.text('manual_submit_called=false'), findsOneWidget);
    expect(find.text('scheduler_real_order_enabled=false'), findsOneWidget);
    expect(find.text('requires_manual_confirm=true'), findsOneWidget);
    expect(find.text('Submit Live KIS Order'), findsNothing);

    controller.dispose();
  });

  testWidgets('Run Preflight Once calls readiness endpoint without order input',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 1800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeReadinessApiClient();
    final controller = _readinessController(api)
      ..orderTicketSymbol = '999999'
      ..orderTicketQty = 99
      ..orderTicketSide = 'sell';

    await tester.pumpWidget(_wrap(controller));

    await tester.ensureVisible(find.text('Run Preflight Once'));
    await tester.tap(find.text('Run Preflight Once'));
    await tester.pumpAndSettle();

    expect(api.preflightCalls, 1);
    expect(api.validationCalls, 0);
    expect(controller.kisAutoReadinessResult?.preflight, isTrue);
    expect(controller.kisAutoReadinessResult?.realOrderSubmitAllowed, isFalse);
    expect(find.text('pr15_no_live_auto_submit_path'), findsWidgets);
    expect(find.text('999999'), findsNothing);
    expect(find.text('real_order_submit_allowed=false'), findsOneWidget);

    controller.dispose();
  });
}

DashboardController _readinessController(_FakeReadinessApiClient api) {
  return DashboardController(api, autoload: false)
    ..selectedProvider = SelectedProvider.kis
    ..krWatchlist = _krWatchlist
    ..kisAutoReadinessResult = KisAutoReadiness.fromJson(_readinessJson())
    ..kisAutoReadinessLoaded = true;
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

class _FakeReadinessApiClient extends ApiClient {
  int preflightCalls = 0;
  int refreshCalls = 0;
  int validationCalls = 0;

  @override
  Future<KisAutoReadiness> fetchKisAutoReadiness() async {
    refreshCalls += 1;
    return KisAutoReadiness.fromJson(_readinessJson());
  }

  @override
  Future<KisAutoReadiness> runKisAutoPreflightOnce() async {
    preflightCalls += 1;
    return KisAutoReadiness.fromJson(_readinessJson(
      preflight: true,
      reason: 'pr15_no_live_auto_submit_path',
      futureReady: true,
    ));
  }

  @override
  Future<List<TradingRun>> getRecentTradingRuns() async => const [];
}

Map<String, dynamic> _readinessJson({
  bool preflight = false,
  String reason = 'live_auto_disabled_by_default',
  bool futureReady = false,
}) {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': preflight ? 'kis_live_auto_preflight' : 'kis_live_auto_readiness',
    'preflight': preflight,
    'checked_at': '2026-05-14T00:00:00Z',
    'auto_order_ready': false,
    'future_auto_order_ready': futureReady,
    'live_auto_enabled': false,
    'real_order_submit_allowed': false,
    'reason': reason,
    'checks': {
      'dry_run': true,
      'kill_switch': false,
      'kis_enabled': true,
      'kis_real_order_enabled': true,
      'kis_scheduler_enabled': false,
      'kis_scheduler_allow_real_orders': false,
      'market_open': true,
      'entry_allowed_now': true,
      'daily_loss_ok': true,
      'trade_limit_ok': true,
      'gpt_context_available': true,
      'risk_engine_ok': true,
      'live_auto_buy_enabled': false,
      'live_auto_sell_enabled': false,
    },
    'safety': {
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'scheduler_real_order_enabled': false,
      'requires_manual_confirm': true,
    },
    'blocked_by': [
      reason,
      'buy_auto_disabled',
      'sell_auto_disabled',
      'pr15_no_live_auto_submit_path',
    ],
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
