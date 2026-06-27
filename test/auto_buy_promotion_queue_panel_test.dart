import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

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

    expect(find.byKey(const ValueKey('auto-buy-promotion-queue-panel')),
        findsOneWidget);
    expect(find.text('Auto Buy Promotion Queue'), findsOneWidget);
    expect(find.text('PROMOTION ONLY'), findsOneWidget);
    expect(find.text('REVIEW REQUIRED'), findsWidgets);
    expect(find.text('NOT AN ORDER'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsOneWidget);
    expect(find.text('LIVE CONVERSION REQUIRES FINAL CONFIRMATION'),
        findsOneWidget);
    expect(find.text('SCHEDULER REAL ORDERS DISABLED'), findsOneWidget);
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

    await tester.tap(find.text('Convert via Guarded Live Buy').last);
    await tester.pumpAndSettle();

    expect(api.liveReadinessCalls, 2);
    expect(api.liveRunCalls, 1);
    expect(api.lastPromotionId, 1);
    expect(api.markConvertedCalls, 0);
    expect(api.manualSubmitCalls, 0);

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

    expect(find.text('CONVERTED'), findsWidgets);
    expect(find.text('live_order_created'), findsOneWidget);
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
  _PromotionQueueApiClient({this.promotionStatus = 'pending'});

  final String promotionStatus;

  int operationsCalls = 0;
  int promotionsCalls = 0;
  int markReviewedCalls = 0;
  int dismissCalls = 0;
  int liveReadinessCalls = 0;
  int liveRunCalls = 0;
  int liveRecentCalls = 0;
  int markConvertedCalls = 0;
  int manualSubmitCalls = 0;
  int? lastPromotionId;

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
