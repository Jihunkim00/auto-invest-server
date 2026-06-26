import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/auto_buy_scheduler_panel.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_operations.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_promotion.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_scheduler.dart';

import 'auto_buy_operations_model_test.dart';
import 'auto_buy_promotion_model_test.dart';
import 'auto_buy_scheduler_model_test.dart';

void main() {
  testWidgets('auto buy scheduler panel renders dry-run safety state',
      (tester) async {
    final api = _SchedulerApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyScheduler(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuySchedulerPanel(controller: controller)),
    ));

    expect(
        find.byKey(const ValueKey('auto-buy-scheduler-panel')), findsOneWidget);
    expect(find.text('Auto Buy Scheduler'), findsOneWidget);
    expect(find.text('DRY-RUN ONLY'), findsOneWidget);
    expect(find.text('PROMOTION QUEUE ONLY'), findsOneWidget);
    expect(find.text('NO LIVE ORDERS'), findsOneWidget);
    expect(find.text('SCHEDULER REAL ORDERS DISABLED'), findsOneWidget);
    expect(find.text('Enable Dry-Run Scheduler'), findsOneWidget);
    expect(find.text('Refresh Scheduler Status'), findsOneWidget);
    expect(find.text('Run Dry-Run Once'), findsOneWidget);
    expect(find.text('Enable Live Scheduler'), findsNothing);
    expect(find.text('Run Live Buy'), findsNothing);
    expect(find.text('Submit Order'), findsNothing);
    expect(find.text('Confirm Live Order'), findsNothing);
    expect(find.text('Enable Real Orders'), findsNothing);
    expect(find.text('Enable Real Auto Buy'), findsNothing);

    controller.dispose();
  });

  testWidgets('scheduler panel run button calls dry-run endpoint only',
      (tester) async {
    final api = _SchedulerApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyScheduler(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuySchedulerPanel(controller: controller)),
    ));

    await tester.tap(find.byKey(
      const ValueKey('run-scheduled-dry-run-once-button'),
    ));
    await tester.pumpAndSettle();

    expect(api.runDryRunCalls, 1);
    expect(api.liveRunCalls, 0);
    expect(api.fetchPromotionsCalls, 1);
    expect(api.fetchOperationsCalls, 1);

    controller.dispose();
  });

  testWidgets('enable sends only dry-run scheduler setting payload',
      (tester) async {
    final api = _SchedulerApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyScheduler(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuySchedulerPanel(controller: controller)),
    ));

    await tester.tap(find.byKey(
      const ValueKey('enable-dry-run-scheduler-button'),
    ));
    await tester.pumpAndSettle();

    expect(api.updateSettingsPayloads, [
      {'strategy_auto_buy_scheduler_enabled': true},
    ]);
    expect(api.schedulerEnabled, isTrue);
    expect(find.text('Disable Scheduler'), findsOneWidget);
    expect(find.text('Enable Dry-Run Scheduler'), findsNothing);

    controller.dispose();
  });

  testWidgets('disable sends only dry-run scheduler setting payload',
      (tester) async {
    final api = _SchedulerApiClient(schedulerEnabled: true);
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyScheduler(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuySchedulerPanel(controller: controller)),
    ));

    expect(find.text('Disable Scheduler'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('disable-scheduler-button')));
    await tester.pumpAndSettle();

    expect(api.updateSettingsPayloads, [
      {'strategy_auto_buy_scheduler_enabled': false},
    ]);
    expect(api.schedulerEnabled, isFalse);
    expect(find.text('Enable Dry-Run Scheduler'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('settings update failure rolls back and refreshes server status',
      (tester) async {
    final api = _SchedulerApiClient(updateThrows: true);
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyScheduler(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuySchedulerPanel(controller: controller)),
    ));

    await tester.tap(find.byKey(
      const ValueKey('enable-dry-run-scheduler-button'),
    ));
    await tester.pumpAndSettle();

    expect(api.updateSettingsPayloads, [
      {'strategy_auto_buy_scheduler_enabled': true},
    ]);
    expect(api.statusCalls, 2);
    expect(controller.strategyAutoBuySchedulerStatus?.enabled, isFalse);
    expect(find.text('Enable Dry-Run Scheduler'), findsOneWidget);
    expect(find.text('Disable Scheduler'), findsNothing);

    controller.dispose();
  });
}

class _SchedulerApiClient extends ApiClient {
  _SchedulerApiClient({
    this.schedulerEnabled = false,
    this.updateThrows = false,
  });

  bool schedulerEnabled;
  final bool updateThrows;
  int statusCalls = 0;
  int runDryRunCalls = 0;
  int fetchPromotionsCalls = 0;
  int fetchOperationsCalls = 0;
  int liveRunCalls = 0;
  final List<Map<String, dynamic>> updateSettingsPayloads = [];

  @override
  Future<StrategyAutoBuySchedulerStatus> fetchStrategyAutoBuySchedulerStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    statusCalls += 1;
    return StrategyAutoBuySchedulerStatus.fromJson(
      autoBuySchedulerStatusJson(
        enabled: schedulerEnabled,
        blockReason: schedulerEnabled ? null : 'scheduler_disabled',
      ),
    );
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    updateSettingsPayloads.add(Map<String, dynamic>.from(values));
    if (updateThrows) {
      throw const ApiRequestException('settings update failed');
    }
    schedulerEnabled = values['strategy_auto_buy_scheduler_enabled'] == true;
  }

  @override
  Future<StrategyAutoBuySchedulerRunResult>
      runStrategyAutoBuySchedulerDryRunOnce({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
  }) async {
    runDryRunCalls += 1;
    return StrategyAutoBuySchedulerRunResult.fromJson({
      'status': 'ok',
      'action': 'would_buy',
      'provider': 'kis',
      'market': 'KR',
      'created_promotion': true,
      'real_order_submitted': false,
      'validation_called': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'scheduler_run_id': 7,
      'safety': {'read_only': false},
    });
  }

  @override
  Future<StrategyAutoBuyPromotions> fetchStrategyAutoBuyPromotions({
    String provider = 'kis',
    String market = 'KR',
    String status = 'pending',
    String? symbol,
    int limit = 20,
  }) async {
    fetchPromotionsCalls += 1;
    return StrategyAutoBuyPromotions.fromJson(autoBuyPromotionsJson());
  }

  @override
  Future<StrategyAutoBuyOperationsStatus> fetchStrategyAutoBuyOperationsStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    fetchOperationsCalls += 1;
    return StrategyAutoBuyOperationsStatus.fromJson(autoBuyOperationsJson());
  }
}
