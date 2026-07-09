import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/auto_buy_live_phase1_panel.dart';
import 'package:auto_invest_dashboard/models/auto_buy_live_phase1.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_operations.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_promotion.dart';

import 'auto_buy_live_phase1_model_test.dart';
import 'auto_buy_operations_model_test.dart';
import 'auto_buy_promotion_model_test.dart';

void main() {
  testWidgets('phase one panel renders locked safety posture', (tester) async {
    _setLargeViewport(tester);
    final api = _Phase1ApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshAutoBuyLivePhase1(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyLivePhase1Panel(controller: controller)),
    ));

    expect(find.byKey(const ValueKey('auto-buy-live-phase1-panel')),
        findsOneWidget);
    expect(find.text('자동매수 1단계'), findsOneWidget);
    expect(find.text('기본 비활성화'), findsWidgets);
    expect(find.text('하루 최대 1회'), findsOneWidget);
    expect(find.text('보유 종목 우선 점검'), findsOneWidget);
    expect(find.text('준비 점검 필요'), findsOneWidget);
    expect(find.text('브로커 제출 없음'), findsWidgets);
    expect(find.text('자동 재시도 없음'), findsWidgets);
    expect(find.text('자동매수 1단계 상태 새로고침'), findsWidgets);
    expect(find.text('1단계 1회 시도'), findsOneWidget);
    expect(find.text('Enable KIS Real Orders'), findsNothing);
    expect(find.text('Turn Off Dry Run'), findsNothing);
    expect(find.text('Disable Kill Switch'), findsNothing);
    expect(find.text('Force Buy'), findsNothing);
    expect(find.text('Retry Buy'), findsNothing);
    expect(find.text('Auto Sell'), findsNothing);

    controller.dispose();
  });

  testWidgets('phase one run button calls phase endpoint only once',
      (tester) async {
    _setLargeViewport(tester);
    final api = _Phase1ApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshAutoBuyLivePhase1(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyLivePhase1Panel(controller: controller)),
    ));

    await tester.tap(find.byKey(const ValueKey('run-auto-buy-phase1-once')));
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(api.lastConfirmPhase1Run, isTrue);
    expect(api.lastTriggerSource, 'manual_phase1_test');
    expect(api.promotionsCalls, 1);
    expect(api.operationsCalls, 1);
    expect(api.settingsMutationCalls, 0);
    expect(api.legacyGuardedBuyCalls, 0);
    expect(find.text('실주문 제출됨'), findsWidgets);
    expect(find.text('KIS-ORDER-1'), findsWidgets);
    expect(find.text('Retry Order'), findsNothing);
    expect(find.text('Submit Again'), findsNothing);
    expect(find.text('Force Convert'), findsNothing);

    controller.dispose();
  });
}

void _setLargeViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 1400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _Phase1ApiClient extends ApiClient {
  int statusCalls = 0;
  int runCalls = 0;
  int promotionsCalls = 0;
  int operationsCalls = 0;
  int settingsMutationCalls = 0;
  int legacyGuardedBuyCalls = 0;
  bool? lastConfirmPhase1Run;
  String? lastTriggerSource;

  @override
  Future<AutoBuyLivePhase1Result> fetchAutoBuyLivePhase1Status({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    statusCalls += 1;
    return AutoBuyLivePhase1Result.fromJson(
      runCalls == 0
          ? autoBuyLivePhase1Json()
          : autoBuyLivePhase1Json(
              enabled: true,
              status: 'submitted',
              realOrderSubmitted: true,
              brokerSubmitCalled: true,
              selectedPromotionId: 7,
              selectedSymbol: '005930',
              orderId: 55,
              brokerOrderId: 'KIS-ORDER-1',
              dailyCount: 1,
            ),
    );
  }

  @override
  Future<AutoBuyLivePhase1Result> runAutoBuyLivePhase1Once({
    String provider = 'kis',
    String market = 'KR',
    int? promotionId,
    String triggerSource = 'manual_phase1_test',
    String language = 'ko',
    String locale = 'ko-KR',
    bool confirmPhase1Run = true,
  }) async {
    runCalls += 1;
    lastConfirmPhase1Run = confirmPhase1Run;
    lastTriggerSource = triggerSource;
    return AutoBuyLivePhase1Result.fromJson(
      autoBuyLivePhase1Json(
        enabled: true,
        status: 'submitted',
        realOrderSubmitted: true,
        brokerSubmitCalled: true,
        selectedPromotionId: promotionId ?? 7,
        selectedSymbol: '005930',
        orderId: 55,
        brokerOrderId: 'KIS-ORDER-1',
        dailyCount: 1,
      ),
    );
  }

  @override
  Future<StrategyAutoBuyPromotions> fetchStrategyAutoBuyPromotions({
    String provider = 'kis',
    String market = 'KR',
    String status = 'pending',
    String? symbol,
    int limit = 20,
  }) async {
    promotionsCalls += 1;
    return StrategyAutoBuyPromotions.fromJson(autoBuyPromotionsJson());
  }

  @override
  Future<StrategyAutoBuyOperationsStatus> fetchStrategyAutoBuyOperationsStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    operationsCalls += 1;
    return StrategyAutoBuyOperationsStatus.fromJson(autoBuyOperationsJson());
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    settingsMutationCalls += 1;
  }
}
