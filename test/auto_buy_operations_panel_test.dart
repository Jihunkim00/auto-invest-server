import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/auto_buy_operations_panel.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_operations.dart';
import 'package:auto_invest_dashboard/models/strategy_dry_run_auto_buy.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_buy.dart';

import 'auto_buy_operations_model_test.dart';
import 'strategy_dry_run_auto_buy_model_test.dart';
import 'strategy_live_auto_buy_model_test.dart';

void main() {
  testWidgets('auto buy operations panel renders status and guarded actions',
      (tester) async {
    _setLargeViewport(tester);
    final api = _AutoBuyOpsApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyOperationsPanel(controller: controller)),
    ));

    expect(find.text('Auto Buy Operations'), findsOneWidget);
    expect(find.text('AUTO BUY OPS'), findsOneWidget);
    expect(find.text('DRY RUN EVIDENCE REQUIRED'), findsOneWidget);
    expect(find.text('TARGET RISK GATED'), findsOneWidget);
    expect(find.text('KIS VALIDATION REQUIRED'), findsOneWidget);
    expect(find.text('ONE SHOT LIVE BUY'), findsOneWidget);
    expect(find.text('SCHEDULED DRY RUN'), findsOneWidget);
    expect(find.text('PROMOTION ONLY'), findsOneWidget);
    expect(find.text('NO LIVE SCHEDULER'), findsOneWidget);
    expect(find.text('NO AUTO RETRY'), findsOneWidget);
    expect(find.text('READY FOR OPERATOR CONFIRM'), findsWidgets);
    expect(find.textContaining('005930'), findsWidgets);

    await tester.tap(find.byKey(
      const ValueKey('run-dry-run-auto-buy-once-button'),
    ));
    await tester.pumpAndSettle();

    expect(api.dryRunCalls, 1);
    expect(api.operationsCalls, greaterThanOrEqualTo(2));
    expect(api.settingMutationCalls, 0);

    controller.dispose();
  });

  testWidgets('guarded live auto buy button requires final confirmation',
      (tester) async {
    _setLargeViewport(tester);
    final api = _AutoBuyOpsApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyOperationsPanel(controller: controller)),
    ));

    await tester.tap(find.byKey(
      const ValueKey('run-guarded-live-auto-buy-once-button'),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('auto-buy-live-confirm-dialog')),
        findsOneWidget);
    expect(api.liveRunCalls, 0);

    await tester.tap(find.text('Run Guarded Live Auto Buy Once').last);
    await tester.pumpAndSettle();

    expect(api.liveReadinessCalls, 2);
    expect(api.liveRunCalls, 1);
    expect(api.liveRecentCalls, 2);
    expect(api.settingMutationCalls, 0);

    controller.dispose();
  });

  testWidgets(
      'guarded live auto buy button is disabled when readiness is blocked',
      (tester) async {
    _setLargeViewport(tester);
    final api = _AutoBuyOpsApiClient(ready: false);
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyOperationsPanel(controller: controller)),
    ));

    final button = tester.widget<FilledButton>(find.byKey(
      const ValueKey('run-guarded-live-auto-buy-once-button'),
    ));
    expect(button.onPressed, isNull);
    expect(api.liveRunCalls, 0);

    controller.dispose();
  });
}

void _setLargeViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 900);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _AutoBuyOpsApiClient extends ApiClient {
  _AutoBuyOpsApiClient({this.ready = true});

  final bool ready;
  int operationsCalls = 0;
  int dryRunCalls = 0;
  int dryRecentCalls = 0;
  int liveReadinessCalls = 0;
  int liveRunCalls = 0;
  int liveRecentCalls = 0;
  int settingMutationCalls = 0;

  @override
  Future<StrategyAutoBuyOperationsStatus> fetchStrategyAutoBuyOperationsStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    operationsCalls += 1;
    return StrategyAutoBuyOperationsStatus.fromJson(
      autoBuyOperationsJson(
        ready: ready,
        stage: ready ? 'ready_for_operator_confirm' : 'live_readiness_blocked',
        nextAction: ready
            ? 'confirm_guarded_live_buy'
            : 'enable_prerequisites_manually',
      ),
    );
  }

  @override
  Future<StrategyDryRunAutoBuyResult> runStrategyDryRunAutoBuy({
    String? profileName,
    String? symbol,
  }) async {
    dryRunCalls += 1;
    return StrategyDryRunAutoBuyResult.fromJson(dryRunResultJson());
  }

  @override
  Future<StrategyDryRunAutoBuyRecent> fetchStrategyDryRunAutoBuyRecent({
    String provider = 'kis',
    String market = 'KR',
    String? profileName,
    String? symbol,
    int limit = 20,
  }) async {
    dryRecentCalls += 1;
    return StrategyDryRunAutoBuyRecent.fromJson({
      'provider': 'kis',
      'market': 'KR',
      'count': 1,
      'items': [dryRunResultJson()],
      'safety': {'read_only': true},
    });
  }

  @override
  Future<StrategyLiveAutoBuyReadiness> fetchStrategyLiveAutoBuyReadiness({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    int? sourceDryRunId,
  }) async {
    liveReadinessCalls += 1;
    return StrategyLiveAutoBuyReadiness.fromJson(
      liveReadinessJson(ready: ready),
    );
  }

  @override
  Future<StrategyLiveAutoBuyRunResult> runStrategyLiveAutoBuyOnce({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    int? promotionId,
    int? sourceDryRunId,
    double? maxNotionalKrw,
    String triggerSource = 'flutter_dashboard',
    String? clientRequestId,
  }) async {
    liveRunCalls += 1;
    return StrategyLiveAutoBuyRunResult.fromJson(
      liveRunResultJson(status: 'submitted', submitted: true),
    );
  }

  @override
  Future<StrategyLiveAutoBuyRecent> fetchStrategyLiveAutoBuyRecent({
    String provider = 'kis',
    String market = 'KR',
    int limit = 20,
  }) async {
    liveRecentCalls += 1;
    return StrategyLiveAutoBuyRecent.fromJson({
      'provider': 'kis',
      'market': 'KR',
      'count': 1,
      'items': [liveRunResultJson(status: 'submitted', submitted: true)],
      'safety': {'read_only': true},
    });
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    settingMutationCalls += 1;
    throw StateError('auto buy operations must not update settings');
  }
}
