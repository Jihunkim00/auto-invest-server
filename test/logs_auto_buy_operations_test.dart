import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/logs_screen.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_operations.dart';

import 'auto_buy_operations_model_test.dart';

void main() {
  testWidgets('Logs screen loads and shows auto buy operations panel',
      (tester) async {
    final api = _LogsAutoBuyOpsApiClient();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: LogsScreen(controller: controller)),
    ));
    await tester.pumpAndSettle();

    expect(api.operationsCalls, 1);
    expect(api.recentRunsLimit, 50);
    expect(find.text('Logs'), findsOneWidget);
    expect(find.text('Auto Buy Operations'), findsOneWidget);
    expect(find.text('AUTO BUY OPS'), findsOneWidget);
    expect(find.text('Run Dry-Run Auto Buy Once'), findsOneWidget);
    expect(find.text('Run Guarded Live Auto Buy Once'), findsOneWidget);
    expect(find.text('Enable Scheduler'), findsNothing);
    expect(find.text('Turn Off Dry Run'), findsNothing);
    expect(find.text('Disable Kill Switch'), findsNothing);
    expect(find.text('Enable KIS Real Order'), findsNothing);
    expect(find.text('Retry Submit'), findsNothing);
    expect(find.text('Submit Again'), findsNothing);

    controller.dispose();
  });
}

class _LogsAutoBuyOpsApiClient extends ApiClient {
  int operationsCalls = 0;
  int? recentRunsLimit;

  @override
  Future<List<TradingLogItem>> fetchRecentRuns({int limit = 20}) async {
    recentRunsLimit = limit;
    return const [];
  }

  @override
  Future<List<OrderLogItem>> fetchRecentOrders({int limit = 20}) async {
    return const [];
  }

  @override
  Future<List<SignalLogItem>> fetchRecentSignals({int limit = 20}) async {
    return const [];
  }

  @override
  Future<LogsSummary> fetchLogsSummary() async => const LogsSummary(
        latestRun: null,
        latestOrder: null,
        latestSignal: null,
        counts: {'runs': 0, 'orders': 0, 'signals': 0},
      );

  @override
  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async =>
      KisSchedulerSimulationStatus.safeDefault();

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async =>
      KisManualOrderSafetyStatus.safeDefault;

  @override
  Future<StrategyAutoBuyOperationsStatus>
      fetchStrategyAutoBuyOperationsStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    operationsCalls += 1;
    return StrategyAutoBuyOperationsStatus.fromJson(autoBuyOperationsJson());
  }
}
