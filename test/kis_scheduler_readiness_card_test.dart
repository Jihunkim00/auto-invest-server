import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_readiness.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('fetchKisSchedulerReadiness calls readiness endpoint only', () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_readinessJson()), 200);
      }),
    );

    final result = await client.fetchKisSchedulerReadiness();

    expect(captured.method, 'GET');
    expect(captured.url.path, '/kis/scheduler/readiness');
    expect(captured.url.queryParameters['include_modules'], 'true');
    expect(captured.url.queryParameters['include_recent_runs'], 'true');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/validate')));
    expect(result.mode, 'kis_scheduler_readiness');
    expect(result.schedulerRealOrdersEnabled, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
  });

  testWidgets('scheduler readiness card renders disabled no-submit audit',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 6400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerReadinessApi();
    final controller = _controller(api)
      ..latestKisSchedulerReadiness =
          KisSchedulerReadiness.fromJson(_readinessJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_readiness_card'));
    expect(card, findsOneWidget);
    for (final label in [
      'SCHEDULER READINESS',
      'SCHEDULE AUDIT',
      'READINESS ONLY',
      'REAL ORDERS DISABLED',
      'NO BROKER SUBMIT',
      'DRY-RUN SAFE',
      'DEFAULT OFF',
    ]) {
      expect(
          find.descendant(of: card, matching: find.text(label)), findsWidgets);
    }
    expect(find.descendant(of: card, matching: find.text('DISABLED')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('scheduler_disabled')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('buy_readiness')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('DRY-RUN ONLY')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('Limited Auto Sell')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('Limited Auto Buy')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('Execution reviews')),
        findsOneWidget);
    expect(find.text('Broker submit: No'), findsOneWidget);
    expect(find.text('Real order submitted: No'), findsOneWidget);
    expect(find.text('Developer Raw Payload'), findsOneWidget);
    expect(find.textContaining('"provider": "kis"'), findsNothing);
    expect(find.text('Enable Scheduler Real Orders'), findsNothing);

    controller.dispose();
  });

  testWidgets('scheduler readiness refresh action calls API without submit',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 6400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerReadinessApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    final button = find.descendant(
      of: find.byKey(const Key('kis_scheduler_readiness_card')),
      matching: find.text('Refresh Scheduler Readiness'),
    );
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(api.readinessCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(
        find.descendant(
          of: find.byKey(const Key('kis_scheduler_readiness_card')),
          matching: find.text('REAL ORDERS DISABLED'),
        ),
        findsOneWidget);
    expect(
        find.text(
            'No scheduler readiness data yet. Default scheduler state remains off.'),
        findsNothing);

    controller.dispose();
  });

  testWidgets('scheduler readiness empty module state does not crash',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 4200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(_FakeSchedulerReadinessApi())
      ..latestKisSchedulerReadiness =
          KisSchedulerReadiness.fromJson(_readinessJson(empty: true));

    await tester.pumpWidget(_wrap(controller));

    expect(
        find.byKey(const Key('kis_scheduler_readiness_card')), findsOneWidget);
    expect(find.text('No scheduler slots returned.'), findsOneWidget);
    expect(find.text('UNAVAILABLE'), findsWidgets);
    expect(find.text('No recent scheduler runs returned.'), findsOneWidget);

    controller.dispose();
  });
}

DashboardController _controller(_FakeSchedulerReadinessApi api) {
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

class _FakeSchedulerReadinessApi extends ApiClient {
  int readinessCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisSchedulerReadiness> fetchKisSchedulerReadiness({
    bool includeModules = true,
    bool includeRecentRuns = true,
    bool includeRaw = false,
  }) async {
    readinessCalls += 1;
    return KisSchedulerReadiness.fromJson(_readinessJson());
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

Map<String, dynamic> _readinessJson({bool empty = false}) {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_scheduler_readiness',
    'readiness_only': true,
    'scheduler_real_orders_enabled': false,
    'real_order_submit_allowed': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'summary': {
      'scheduler_enabled': false,
      'kis_scheduler_enabled': false,
      'kis_scheduler_dry_run': true,
      'kis_scheduler_allow_real_orders': false,
      'scheduler_real_orders_enabled': false,
      'market_open': false,
      'entry_allowed_now': false,
      'sell_session_allowed': false,
      'next_scheduled_slot': empty
          ? null
          : {
              'slot_id': 'open_phase_buy_readiness',
              'label': 'open_phase buy readiness',
              'scheduled_time': '09:05',
              'timezone': 'Asia/Seoul',
              'purpose': 'buy_readiness',
              'enabled': false,
              'real_order_allowed': false,
              'dry_run_only': true,
            },
      'current_slot_label': null,
      'real_order_submit_allowed': false,
      'readiness_status': 'DISABLED',
      'primary_block_reason': 'scheduler_disabled',
      'block_reasons': ['scheduler_disabled'],
    },
    'schedule': empty
        ? []
        : [
            {
              'slot_id': 'open_phase_buy_readiness',
              'label': 'open_phase buy readiness',
              'scheduled_time': '09:05',
              'timezone': 'Asia/Seoul',
              'purpose': 'buy_readiness',
              'enabled': false,
              'real_order_allowed': false,
              'dry_run_only': true,
              'notes': ['scheduler_would_call_readiness_only'],
            },
          ],
    'modules': empty
        ? {}
        : {
            'limited_auto_sell': {
              'available': true,
              'status_endpoint': '/kis/limited-auto-sell/status',
              'stop_loss_execution_enabled': false,
              'take_profit_execution_enabled': false,
              'live_auto_sell_enabled': false,
              'dry_run': true,
              'daily_limit_remaining': 1,
              'ready_for_scheduler_dry_run': true,
              'ready_for_scheduler_real_order': false,
              'block_reasons': ['dry_run_true'],
            },
            'limited_auto_buy': {
              'available': true,
              'status_endpoint': '/kis/limited-auto-buy/status',
              'auto_buy_execution_enabled': false,
              'live_auto_buy_enabled': false,
              'dry_run': true,
              'daily_limit_remaining': 1,
              'ready_for_scheduler_dry_run': true,
              'ready_for_scheduler_real_order': false,
              'block_reasons': ['auto_buy_execution_disabled'],
            },
            'portfolio_position_management': {
              'available': true,
              'read_only': true,
            },
            'execution_review': {
              'available': true,
              'read_only': true,
            },
          },
    'block_reasons': ['scheduler_disabled'],
    'safety': {
      'readiness_only': true,
      'no_broker_submit_from_scheduler_readiness': true,
      'scheduler_real_orders_enabled': false,
      'kis_scheduler_allow_real_orders': false,
      'manual_submit_called': false,
      'broker_submit_called': false,
      'real_order_submitted': false,
      'live_auto_buy_default_safe': true,
      'live_auto_sell_default_safe': true,
      'kill_switch': false,
      'dry_run': true,
      'runtime_defaults_safe': true,
      'existing_buy_execution_unchanged': true,
      'existing_sell_execution_unchanged': true,
    },
    'recent_runs': empty
        ? []
        : [
            {
              'created_at': '2026-05-24T00:00:00',
              'trigger_source': 'kis_scheduler_live',
              'mode': 'kis_scheduler_live_once',
              'result': 'blocked',
              'symbol': '005930',
              'action': 'hold',
              'real_order_submitted': false,
              'broker_submit_called': false,
              'manual_submit_called': false,
              'block_reasons': ['kis_scheduler_live_disabled'],
            },
          ],
    'diagnostics': {},
  };
}
