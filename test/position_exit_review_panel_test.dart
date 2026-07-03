import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/position_exit_review_panel.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/position_exit_review.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_buy.dart';

import 'position_exit_review_model_test.dart';

void main() {
  testWidgets('position exit review panel renders Korean labels and position',
      (tester) async {
    _setLargeViewport(tester);
    final api = _PositionExitReviewApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshPositionExitReview(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: PositionExitReviewPanel(controller: controller)),
    ));

    expect(find.byKey(const ValueKey('position-exit-review-panel')),
        findsOneWidget);
    expect(find.text('포지션 청산 검토'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('position-exit-review-held-positions-section')),
      findsOneWidget,
    );
    expect(find.text('보유 포지션'), findsOneWidget);
    expect(find.text('매도 사전 점검'), findsOneWidget);
    expect(find.text('사전 점검 전용'), findsOneWidget);
    expect(find.text('실주문 없음'), findsOneWidget);
    expect(find.text('브로커 제출 없음'), findsOneWidget);
    expect(find.text('최종 확인 필요'), findsOneWidget);
    expect(find.textContaining('005930'), findsWidgets);
    expect(find.text('보유 수량'), findsOneWidget);
    expect(find.text('현재가'), findsOneWidget);
    expect(find.text('평가손익'), findsWidgets);
    expect(
      find.byKey(
        const ValueKey('position-exit-review-sell-preflight-button'),
      ),
      findsOneWidget,
    );
    expect(find.text('Sell Now'), findsNothing);
    expect(find.text('Force Sell'), findsNothing);
    expect(find.text('Auto Sell'), findsNothing);
    expect(find.text('Liquidate All'), findsNothing);
    expect(find.text('Retry Sell'), findsNothing);
    expect(find.text('Enable Live Scheduler'), findsNothing);

    controller.dispose();
  });

  testWidgets('sell preflight button calls only sell preflight endpoint',
      (tester) async {
    _setLargeViewport(tester);
    final api = _PositionExitReviewApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshPositionExitReview(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: PositionExitReviewPanel(controller: controller)),
    ));

    final preflightButton = find.byKey(
      const ValueKey('position-exit-review-sell-preflight-button'),
    );
    await tester.ensureVisible(preflightButton);
    await tester.pumpAndSettle();
    await tester.tap(preflightButton);
    await tester.pumpAndSettle();

    expect(api.preflightCalls, 1);
    expect(api.lastPreflightSymbol, '005930');
    expect(api.liveBuyCalls, 0);
    expect(api.manualSubmitCalls, 0);
    expect(api.sentConfirmLive, isFalse);
    final resultPanel = find.byKey(
      const ValueKey('position-exit-review-preflight-result-panel'),
    );
    expect(resultPanel, findsOneWidget);
    expect(
      find.descendant(of: resultPanel, matching: find.text('매도 사전 점검')),
      findsOneWidget,
    );
    expect(find.text('실주문 없음'), findsWidgets);
    expect(find.text('브로커 제출 없음'), findsWidgets);
    expect(find.text('최종 확인 필요'), findsWidgets);
    expect(find.text('요청 수량'), findsOneWidget);
    expect(find.text('매도 가능 수량'), findsWidgets);
    expect(find.text('예상 매도 금액'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('position-exit-review-checklist')),
      findsOneWidget,
    );
    expect(find.text('점검 목록'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('blocked preflight shows primary block reason', (tester) async {
    _setLargeViewport(tester);
    final api = _PositionExitReviewApiClient(
      preflightStatus: 'blocked',
      primaryBlockReason: 'duplicate_open_sell_order',
    );
    final controller = DashboardController(api, autoload: false);
    await controller.refreshPositionExitReview(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: PositionExitReviewPanel(controller: controller)),
    ));

    final preflightButton = find.byKey(
      const ValueKey('position-exit-review-sell-preflight-button'),
    );
    await tester.ensureVisible(preflightButton);
    await tester.pumpAndSettle();
    await tester.tap(preflightButton);
    await tester.pumpAndSettle();

    final resultPanel = find.byKey(
      const ValueKey('position-exit-review-preflight-result-panel'),
    );
    final primaryBlockReason = find.descendant(
      of: resultPanel,
      matching: find.byKey(
        const ValueKey('position-exit-review-primary-block-reason'),
      ),
    );
    expect(resultPanel, findsOneWidget);
    expect(primaryBlockReason, findsOneWidget);
    expect(
      find.descendant(
        of: primaryBlockReason,
        matching: find.text('주요 차단 사유'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: resultPanel,
        matching: find.text('duplicate_open_sell_order'),
      ),
      findsWidgets,
    );
    expect(api.liveBuyCalls, 0);
    expect(api.manualSubmitCalls, 0);

    controller.dispose();
  });

  testWidgets('position exit review panel renders English labels',
      (tester) async {
    _setLargeViewport(tester);
    final api = _PositionExitReviewApiClient(
      preflightStatus: 'blocked',
      primaryBlockReason: 'duplicate_open_sell_order',
    );
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    );
    await controller.refreshPositionExitReview(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: PositionExitReviewPanel(controller: controller)),
    ));

    expect(find.text('Position Exit Review'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('position-exit-review-held-positions-section')),
      findsOneWidget,
    );
    expect(find.text('Held Positions'), findsOneWidget);
    expect(find.text('Sell Preflight'), findsOneWidget);
    expect(find.text('Preflight Only'), findsOneWidget);
    expect(find.text('No Live Order Submitted'), findsOneWidget);
    expect(find.text('No Broker Submit'), findsOneWidget);
    expect(find.text('Final Confirmation Required'), findsOneWidget);

    final preflightButton = find.byKey(
      const ValueKey('position-exit-review-sell-preflight-button'),
    );
    await tester.ensureVisible(preflightButton);
    await tester.pumpAndSettle();
    await tester.tap(preflightButton);
    await tester.pumpAndSettle();

    final resultPanel = find.byKey(
      const ValueKey('position-exit-review-preflight-result-panel'),
    );
    expect(resultPanel, findsOneWidget);
    expect(
      find.descendant(of: resultPanel, matching: find.text('Sell Preflight')),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: resultPanel,
        matching: find.text('Primary Block Reason'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(of: resultPanel, matching: find.text('Checklist')),
      findsOneWidget,
    );

    controller.dispose();
  });
}

void _setLargeViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 1000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _PositionExitReviewApiClient extends ApiClient {
  _PositionExitReviewApiClient({
    this.preflightStatus = 'allowed',
    this.primaryBlockReason,
  });

  final String preflightStatus;
  final String? primaryBlockReason;
  int reviewCalls = 0;
  int preflightCalls = 0;
  int liveBuyCalls = 0;
  int manualSubmitCalls = 0;
  String? lastPreflightSymbol;
  bool sentConfirmLive = false;

  @override
  Future<PositionExitReview> fetchPositionExitReview() async {
    reviewCalls += 1;
    return PositionExitReview.fromJson(positionExitReviewJson());
  }

  @override
  Future<PositionSellPreflightResult> runPositionSellPreflight({
    required String symbol,
    String provider = 'kis',
    String market = 'KR',
    String quantityMode = 'full',
    double? quantity,
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    preflightCalls += 1;
    lastPreflightSymbol = symbol;
    sentConfirmLive = false;
    return PositionSellPreflightResult.fromJson(
      positionSellPreflightJson(
        status: preflightStatus,
        primaryBlockReason: primaryBlockReason,
      ),
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
    liveBuyCalls += 1;
    throw StateError('position exit review must not run live buy');
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
    manualSubmitCalls += 1;
    throw StateError('position exit review must not submit manual order');
  }
}
