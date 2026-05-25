import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_live.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('runKisSchedulerLiveOnce calls scheduler live endpoint', () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_schedulerLiveJson()), 200);
      }),
    );

    final result = await client.runKisSchedulerLiveOnce();

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/scheduler/run-live-once');
    expect(captured.body, '{}');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/validate')));
    expect(result.mode, 'kis_scheduler_live_once');
  });

  testWidgets('scheduler live card shows disabled guarded state',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 4200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeSchedulerLiveApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_live_card'));
    expect(card, findsOneWidget);
    expect(
      find.descendant(
          of: card, matching: find.text('KIS Scheduler Live Automation')),
      findsOneWidget,
    );
    for (final label in [
      'DISABLED BY DEFAULT',
      'REAL ORDERS GATED',
      'BUY/SELL LIMITED',
      'MAX DAILY ORDERS',
      'KILL SWITCH PROTECTED',
      'DRY RUN BLOCKS LIVE',
    ]) {
      expect(
        find.descendant(of: card, matching: find.text(label)),
        findsOneWidget,
      );
    }
    expect(find.text('Enable Scheduler Real Orders'), findsNothing);

    final runButton = find.descendant(
      of: card,
      matching: find.text('Run Scheduler Live Once'),
    );
    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.text('kis_scheduler_live_disabled'), findsWidgets);
    expect(find.textContaining('KIS SCHEDULER LIVE SUBMITTED'), findsNothing);

    controller.dispose();
  });
}

DashboardController _controller(_FakeSchedulerLiveApi api) {
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

class _FakeSchedulerLiveApi extends ApiClient {
  _FakeSchedulerLiveApi({KisSchedulerLiveResult? result})
      : result =
            result ?? KisSchedulerLiveResult.fromJson(_schedulerLiveJson());

  KisSchedulerLiveResult result;
  int runCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisSchedulerLiveResult> runKisSchedulerLiveOnce() async {
    runCalls += 1;
    return result;
  }

  @override
  Future<List<TradingRun>> getRecentTradingRuns() async => const [];

  @override
  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async =>
      KisSchedulerSimulationStatus.safeDefault();

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

Map<String, dynamic> _schedulerLiveJson() {
  return {
    'status': 'ok',
    'mode': 'kis_scheduler_live_once',
    'result': 'blocked',
    'action': 'hold',
    'reason': 'kis_scheduler_live_disabled',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'scheduler_real_order_enabled': false,
    'checks': {
      'kis_scheduler_live_enabled': false,
      'kis_scheduler_allow_real_orders': false,
      'kis_scheduler_allow_limited_auto_buy': false,
      'kis_scheduler_allow_limited_auto_sell': false,
    },
    'safety': {'max_live_orders_per_day': 2},
  };
}
