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

    expect(find.text('자동매수 운영'), findsWidgets);
    expect(find.text('드라이런 근거 필요'), findsOneWidget);
    expect(find.text('목표 위험 게이트 적용'), findsOneWidget);
    expect(find.text('한국투자증권 검증 필요'), findsOneWidget);
    expect(find.text('단발 실매수'), findsOneWidget);
    expect(find.text('예약 드라이런'), findsOneWidget);
    expect(find.text('프로모션 전용'), findsOneWidget);
    expect(find.text('실거래 스케줄러 없음'), findsOneWidget);
    expect(find.text('자동 재시도 없음'), findsOneWidget);
    expect(find.text('운영자 확인 준비'), findsWidgets);
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

    await tester.tap(find.text('보호된 실매수 1회 실행').last);
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
