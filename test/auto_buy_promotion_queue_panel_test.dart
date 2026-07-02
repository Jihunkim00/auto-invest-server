import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/auto_buy_promotion_queue_panel.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_operations.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_promotion.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_buy.dart';

import 'auto_buy_operations_model_test.dart';
import 'auto_buy_promotion_model_test.dart';
import 'strategy_live_auto_buy_model_test.dart';

void main() {
  testWidgets('promotion queue renders pending candidate details',
      (tester) async {
    final api = _PromotionQueueApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    await controller.refreshStrategyAutoBuyPromotions(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyPromotionQueuePanel(controller: controller)),
    ));
    final strings = controller.strings;

    expect(find.byKey(const ValueKey('auto-buy-promotion-queue-panel')),
        findsOneWidget);
    expect(find.text('자동매수 프로모션 검토 목록'), findsOneWidget);
    expect(find.text('프로모션 전용'), findsOneWidget);
    expect(find.text('검토 필요'), findsWidgets);
    expect(find.text('주문 아님'), findsOneWidget);
    expect(find.text(strings.noBrokerSubmit), findsOneWidget);
    expect(find.text('실거래 전환은 최종 확인 필요'), findsOneWidget);
    expect(find.text('스케줄러 실주문 비활성화'), findsOneWidget);
    expect(find.textContaining('005930'), findsWidgets);
    expect(find.text('\u20A930,000'), findsWidgets);
    expect(find.text('3'), findsWidgets);
    expect(find.text('Retry Submit'), findsNothing);
    expect(find.text('Submit Again'), findsNothing);

    controller.dispose();
  });

  testWidgets('promotion queue mark reviewed and dismiss are local actions',
      (tester) async {
    final api = _PromotionQueueApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    await controller.refreshStrategyAutoBuyPromotions(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyPromotionQueuePanel(controller: controller)),
    ));

    final markReviewed =
        find.byKey(const ValueKey('mark-reviewed-promotion-1'));
    await tester.ensureVisible(markReviewed);
    await tester.pumpAndSettle();
    await tester.tap(markReviewed);
    await tester.pumpAndSettle();
    final dismiss = find.byKey(const ValueKey('dismiss-promotion-1'));
    await tester.ensureVisible(dismiss);
    await tester.pumpAndSettle();
    await tester.tap(dismiss);
    await tester.pumpAndSettle();

    expect(api.markReviewedCalls, 1);
    expect(api.dismissCalls, 1);
    expect(api.liveRunCalls, 0);
    expect(api.manualSubmitCalls, 0);

    controller.dispose();
  });

  testWidgets('guarded live auto buy requires final confirmation',
      (tester) async {
    final api = _PromotionQueueApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    await controller.refreshStrategyAutoBuyPromotions(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyPromotionQueuePanel(controller: controller)),
    ));

    final convert =
        find.byKey(const ValueKey('convert-guarded-live-buy-promotion-1'));
    await tester.ensureVisible(convert);
    await tester.pumpAndSettle();
    await tester.tap(convert);
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('promotion-live-confirm-dialog')),
        findsOneWidget);
    expect(api.liveRunCalls, 0);

    await tester
        .tap(find.byKey(const ValueKey('promotion-live-confirm-submit')));
    await tester.pumpAndSettle();

    expect(api.liveReadinessCalls, 2);
    expect(api.liveRunCalls, 1);
    expect(api.liveResultCalls, 1);
    expect(api.lastPromotionId, 1);
    expect(api.markConvertedCalls, 0);
    expect(api.manualSubmitCalls, 0);

    controller.dispose();
  });

  testWidgets('conversion result panel renders Korean labels and syncs safely',
      (tester) async {
    final api = _PromotionQueueApiClient(resultStatus: 'pending_sync');
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    await controller.refreshStrategyAutoBuyPromotions(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyPromotionQueuePanel(controller: controller)),
    ));

    final convert =
        find.byKey(const ValueKey('convert-guarded-live-buy-promotion-1'));
    await tester.ensureVisible(convert);
    await tester.pumpAndSettle();
    await tester.tap(convert);
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('promotion-live-confirm-submit')));
    await tester.pumpAndSettle();

    final strings = controller.strings;
    expect(find.text(strings.liveBuyConversionResult), findsOneWidget);
    expect(find.text(strings.liveOrderSubmitted), findsOneWidget);
    expect(find.text(strings.syncOrderStatus), findsOneWidget);
    expect(find.text('KIS-ORDER-1'), findsWidgets);
    expect(find.byKey(const ValueKey('guarded_live_buy_result_panel')),
        findsOneWidget);
    final syncButton =
        find.byKey(const ValueKey('guarded_live_buy_result_sync_button'));
    expect(syncButton, findsOneWidget);

    await tester.ensureVisible(syncButton);
    await tester.pumpAndSettle();
    await tester.tap(syncButton);
    await tester.pumpAndSettle();

    expect(api.liveResultCalls, 1);
    expect(api.liveResultSyncCalls, 1);
    expect(api.liveRunCalls, 1);
    expect(api.manualSubmitCalls, 0);
    expect(find.text('Retry Order'), findsNothing);
    expect(find.text('Submit Again'), findsNothing);
    expect(find.text('Force Convert'), findsNothing);
    expect(find.text('Auto Retry'), findsNothing);
    expect(find.text('Enable Live Scheduler'), findsNothing);

    controller.dispose();
  });

  testWidgets('blocked conversion result shows no broker submit',
      (tester) async {
    final api = _PromotionQueueApiClient(
      resultStatus: 'blocked',
      resultRealOrderSubmitted: false,
      resultBrokerSubmitCalled: false,
    );
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    await controller.refreshStrategyAutoBuyPromotions(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyPromotionQueuePanel(controller: controller)),
    ));

    final convert =
        find.byKey(const ValueKey('convert-guarded-live-buy-promotion-1'));
    await tester.ensureVisible(convert);
    await tester.pumpAndSettle();
    await tester.tap(convert);
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('promotion-live-confirm-submit')));
    await tester.pumpAndSettle();

    final strings = controller.strings;
    final resultPanel =
        find.byKey(const ValueKey('guarded_live_buy_result_panel'));
    expect(resultPanel, findsOneWidget);
    expect(
      find.descendant(
        of: resultPanel,
        matching: find.text(strings.liveBuyConversionResult),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: resultPanel,
        matching: find.text(strings.noLiveOrderSubmitted),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: resultPanel,
        matching: find.text(strings.noBrokerSubmit),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: resultPanel,
        matching: find.text(strings.liveOrderSubmitted),
      ),
      findsNothing,
    );
    expect(find.byKey(const ValueKey('guarded_live_buy_result_sync_button')),
        findsNothing);
    expect(find.text('KIS-ORDER-1'), findsNothing);
    expect(api.liveRunCalls, 1);
    expect(api.liveResultCalls, 1);
    expect(api.liveResultSyncCalls, 0);
    expect(api.manualSubmitCalls, 0);

    controller.dispose();
  });

  testWidgets('conversion result panel renders English labels', (tester) async {
    final api = _PromotionQueueApiClient(resultStatus: 'pending_sync');
    final controller = DashboardController(api, autoload: false);
    controller.setAppLanguage(AppLanguage.english);
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    await controller.refreshStrategyAutoBuyPromotions(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyPromotionQueuePanel(controller: controller)),
    ));

    final convert =
        find.byKey(const ValueKey('convert-guarded-live-buy-promotion-1'));
    await tester.ensureVisible(convert);
    await tester.pumpAndSettle();
    await tester.tap(convert);
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('promotion-live-confirm-submit')));
    await tester.pumpAndSettle();

    expect(find.text('Live Buy Conversion Result'), findsOneWidget);
    expect(find.text('Live Order Submitted'), findsOneWidget);
    expect(find.text('Sync Order Status'), findsOneWidget);
    expect(find.text('KIS Order No.'), findsOneWidget);
    expect(api.liveRunCalls, 1);
    expect(api.liveResultCalls, 1);

    controller.dispose();
  });

  testWidgets('preflight button renders read-only Korean result',
      (tester) async {
    final api = _PromotionQueueApiClient(preflightStatus: 'allowed');
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    await controller.refreshStrategyAutoBuyPromotions(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyPromotionQueuePanel(controller: controller)),
    ));

    final preflight =
        find.byKey(const ValueKey('preflight-live-buy-promotion-1'));
    await tester.ensureVisible(preflight);
    await tester.pumpAndSettle();
    await tester.tap(preflight);
    await tester.pumpAndSettle();

    expect(api.preflightCalls, 1);
    expect(api.liveRunCalls, 0);
    expect(api.manualSubmitCalls, 0);
    expect(api.lastPreflightPromotionId, 1);
    expect(api.lastPreflightSentConfirmLive, isFalse);
    expect(find.text('매수 전환 사전 점검'), findsOneWidget);
    expect(find.text('사전 점검 결과'), findsOneWidget);
    expect(find.text('실주문 없음'), findsOneWidget);
    expect(find.text('점검 목록'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('blocked preflight disables guarded live conversion',
      (tester) async {
    final api = _PromotionQueueApiClient(
      preflightStatus: 'blocked',
      preflightBlockReason: 'promotion_dismissed',
    );
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    await controller.refreshStrategyAutoBuyPromotions(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyPromotionQueuePanel(controller: controller)),
    ));

    final preflight =
        find.byKey(const ValueKey('preflight-live-buy-promotion-1'));
    await tester.ensureVisible(preflight);
    await tester.pumpAndSettle();
    await tester.tap(preflight);
    await tester.pumpAndSettle();

    final convert =
        find.byKey(const ValueKey('convert-guarded-live-buy-promotion-1'));
    await tester.ensureVisible(convert);
    await tester.pumpAndSettle();
    final button = tester.widget<FilledButton>(convert);

    expect(button.onPressed, isNull);
    expect(api.liveRunCalls, 0);
    expect(find.textContaining('promotion_dismissed'), findsWidgets);

    controller.dispose();
  });

  testWidgets('converted promotion shows trace and hides live action',
      (tester) async {
    final api = _PromotionQueueApiClient(
      promotionStatus: 'live_order_created',
    );
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyAutoBuyOperations(silent: true);
    await controller.refreshStrategyAutoBuyPromotions(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: AutoBuyPromotionQueuePanel(controller: controller)),
    ));

    expect(find.text('전환됨'), findsWidgets);
    expect(find.text('live order created'), findsOneWidget);
    expect(find.textContaining('promotion 1 / dry-run 22'), findsOneWidget);
    expect(find.byKey(const ValueKey('convert-guarded-live-buy-promotion-1')),
        findsNothing);

    controller.dispose();
  });

  testWidgets('dismissed and expired promotions block convert action',
      (tester) async {
    for (final status in ['dismissed', 'expired']) {
      final api = _PromotionQueueApiClient(promotionStatus: status);
      final controller = DashboardController(api, autoload: false);
      await controller.refreshStrategyAutoBuyOperations(silent: true);
      await controller.refreshStrategyAutoBuyPromotions(silent: true);

      await tester.pumpWidget(MaterialApp(
        theme: ThemeData.dark(),
        home:
            Scaffold(body: AutoBuyPromotionQueuePanel(controller: controller)),
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('convert-guarded-live-buy-promotion-1')),
          findsNothing);
      expect(find.textContaining('promotion_'), findsWidgets);
      expect(api.liveRunCalls, 0);

      controller.dispose();
    }
  });
}

class _PromotionQueueApiClient extends ApiClient {
  _PromotionQueueApiClient({
    this.promotionStatus = 'pending',
    this.preflightStatus = 'allowed',
    this.preflightBlockReason,
    this.resultStatus = 'submitted',
    this.resultRealOrderSubmitted = true,
    this.resultBrokerSubmitCalled = true,
  });

  final String promotionStatus;
  final String preflightStatus;
  final String? preflightBlockReason;
  final String resultStatus;
  final bool resultRealOrderSubmitted;
  final bool resultBrokerSubmitCalled;

  int operationsCalls = 0;
  int promotionsCalls = 0;
  int markReviewedCalls = 0;
  int dismissCalls = 0;
  int preflightCalls = 0;
  int liveReadinessCalls = 0;
  int liveRunCalls = 0;
  int liveResultCalls = 0;
  int liveResultSyncCalls = 0;
  int liveRecentCalls = 0;
  int markConvertedCalls = 0;
  int manualSubmitCalls = 0;
  int? lastPromotionId;
  int? lastPreflightPromotionId;
  bool lastPreflightSentConfirmLive = false;

  @override
  Future<StrategyAutoBuyOperationsStatus> fetchStrategyAutoBuyOperationsStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    operationsCalls += 1;
    return StrategyAutoBuyOperationsStatus.fromJson(
      autoBuyOperationsJson(ready: true),
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
    return StrategyAutoBuyPromotions.fromJson(
      autoBuyPromotionsJson(status: promotionStatus),
    );
  }

  @override
  Future<StrategyAutoBuyPromotionActionResult>
      markStrategyAutoBuyPromotionReviewed(int promotionId) async {
    markReviewedCalls += 1;
    return StrategyAutoBuyPromotionActionResult.fromJson({
      'status': 'reviewed',
      'promotion': autoBuyPromotionJson(status: 'reviewed'),
      'safety': {'read_only': true, 'broker_submit_called': false},
    });
  }

  @override
  Future<StrategyAutoBuyPromotionActionResult> dismissStrategyAutoBuyPromotion(
      int promotionId) async {
    dismissCalls += 1;
    return StrategyAutoBuyPromotionActionResult.fromJson({
      'status': 'dismissed',
      'promotion': autoBuyPromotionJson(status: 'dismissed'),
      'safety': {'read_only': true, 'broker_submit_called': false},
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
        liveReadinessJson(ready: true));
  }

  @override
  Future<StrategyLiveAutoBuyPreflightResult> preflightStrategyLiveAutoBuy({
    required int promotionId,
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    int? sourceDryRunId,
    double? maxNotionalKrw,
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    preflightCalls += 1;
    lastPreflightPromotionId = promotionId;
    lastPreflightSentConfirmLive = false;
    return StrategyLiveAutoBuyPreflightResult.fromJson(
      livePreflightJson(
        status: preflightStatus,
        primaryBlockReason: preflightBlockReason,
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
    liveRunCalls += 1;
    lastPromotionId = promotionId;
    return StrategyLiveAutoBuyRunResult.fromJson(
      liveRunResultJson(status: 'submitted', submitted: true),
    );
  }

  @override
  Future<StrategyLiveAutoBuyResult> fetchStrategyLiveAutoBuyResult(
    int attemptId,
  ) async {
    liveResultCalls += 1;
    return StrategyLiveAutoBuyResult.fromJson(
      liveResultJson(
        resultStatus: resultStatus,
        internalStatus:
            resultStatus == 'pending_sync' ? 'UNKNOWN_STALE' : 'SUBMITTED',
        realOrderSubmitted: resultRealOrderSubmitted,
        brokerSubmitCalled: resultBrokerSubmitCalled,
        includeOrder: resultStatus != 'blocked',
      ),
    );
  }

  @override
  Future<StrategyLiveAutoBuyResult> syncStrategyLiveAutoBuyResult(
    int attemptId,
  ) async {
    liveResultSyncCalls += 1;
    return StrategyLiveAutoBuyResult.fromJson(
      liveResultJson(
        resultStatus: 'filled',
        internalStatus: 'FILLED',
        realOrderSubmitted: resultRealOrderSubmitted,
        brokerSubmitCalled: resultBrokerSubmitCalled,
      ),
    );
  }

  @override
  Future<StrategyAutoBuyPromotionActionResult>
      markStrategyAutoBuyPromotionConverted(
    int promotionId, {
    int? promotedToLiveAttemptId,
    int? relatedLiveOrderId,
  }) async {
    markConvertedCalls += 1;
    return StrategyAutoBuyPromotionActionResult.fromJson({
      'status': 'converted_to_live_attempt',
      'promotion': {
        ...autoBuyPromotionJson(status: 'converted_to_live_attempt'),
        'promoted_to_live_attempt_id': promotedToLiveAttemptId,
        'related_live_order_id': relatedLiveOrderId,
      },
      'safety': {'read_only': true, 'broker_submit_called': false},
    });
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
}
