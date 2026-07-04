import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/i18n/app_strings.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/position_lifecycle_panel.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/position_exit_review.dart';
import 'package:auto_invest_dashboard/models/position_lifecycle.dart';

import 'position_lifecycle_model_test.dart';

void main() {
  testWidgets('lifecycle panel renders Korean default labels and summary',
      (tester) async {
    _setLargeViewport(tester);
    final api = _LifecycleApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshPositionLifecycle(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: PositionLifecyclePanel(controller: controller)),
    ));

    final strings = AppStrings(AppLanguage.korean);
    expect(
        find.byKey(const ValueKey('position-lifecycle-panel')), findsOneWidget);
    expect(find.text(strings.positionLifecycle), findsOneWidget);
    expect(find.textContaining(strings.tradeFlowAudit), findsOneWidget);
    expect(find.text(strings.lifecycleOpen), findsWidgets);
    expect(find.text(strings.lifecycleClosed), findsWidgets);
    expect(find.text(strings.realizedPl), findsOneWidget);
    expect(find.text(strings.unrealizedPl), findsOneWidget);
    expect(find.textContaining('005930'), findsOneWidget);
    expect(find.textContaining('\u20A9800'), findsWidgets);
    expect(find.text('Buy'), findsNothing);
    expect(find.text('Sell'), findsNothing);
    expect(find.text('Retry Order'), findsNothing);
    expect(find.text('Force Close'), findsNothing);
    expect(find.text('Liquidate All'), findsNothing);
    expect(find.text('Auto Exit'), findsNothing);
    expect(find.text('Enable Live Scheduler'), findsNothing);

    controller.dispose();
  });

  testWidgets('lifecycle panel renders English labels and timeline in order',
      (tester) async {
    _setLargeViewport(tester);
    final api = _LifecycleApiClient();
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    );
    await controller.refreshPositionLifecycle(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: PositionLifecyclePanel(controller: controller)),
    ));

    expect(find.text('Position Lifecycle'), findsOneWidget);
    expect(find.text('Trade Flow Audit / 2'), findsOneWidget);
    expect(find.text('Open'), findsWidgets);
    expect(find.text('Closed'), findsWidgets);
    expect(find.text('Realized P/L'), findsOneWidget);
    expect(find.text('Unrealized P/L'), findsOneWidget);
    expect(find.text('Average Entry Price'), findsNothing);

    final closedTile = find.byKey(
      const ValueKey(
        'position-lifecycle-expansion-kis:KR:005930:buy-12:sell-42:1',
      ),
    );
    await tester.ensureVisible(closedTile);
    await tester.tap(closedTile);
    await tester.pumpAndSettle();

    expect(find.text('Average Entry Price'), findsOneWidget);
    expect(find.text('Average Exit Price'), findsOneWidget);
    expect(find.text('Holding Period'), findsOneWidget);
    expect(find.text('Related Promotion'), findsOneWidget);
    expect(find.text('Related Order'), findsOneWidget);
    expect(find.text('Audit Trace'), findsOneWidget);

    final promotion = tester.getTopLeft(find.text('Promotion Created'));
    final buy = tester.getTopLeft(find.text('Guarded Buy Submitted'));
    final preflight = tester.getTopLeft(find.text('Sell Preflight'));
    final submitted = tester.getTopLeft(find.text('Guarded Sell Submitted'));
    final filled = tester.getTopLeft(find.text('Sell Filled'));
    final closed = tester.getTopLeft(find.text('Position Closed'));
    expect(promotion.dy < buy.dy, isTrue);
    expect(buy.dy < preflight.dy, isTrue);
    expect(preflight.dy < submitted.dy, isTrue);
    expect(submitted.dy < filled.dy, isTrue);
    expect(filled.dy <= closed.dy, isTrue);

    controller.dispose();
  });

  testWidgets('lifecycle panel shows calculation incomplete for null P/L',
      (tester) async {
    _setLargeViewport(tester);
    final controller = DashboardController(
      _LifecycleApiClient(realizedMissing: true),
      autoload: false,
      initialLanguage: AppLanguage.english,
    );
    await controller.refreshPositionLifecycle(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: PositionLifecyclePanel(controller: controller)),
    ));

    expect(find.textContaining('Calculation Incomplete'), findsWidgets);

    controller.dispose();
  });

  testWidgets('refresh calls only lifecycle read endpoint', (tester) async {
    _setLargeViewport(tester);
    final api = _LifecycleApiClient();
    final controller = DashboardController(
      api,
      autoload: false,
      initialLanguage: AppLanguage.english,
    );
    await controller.refreshPositionLifecycle(silent: true);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: PositionLifecyclePanel(controller: controller)),
    ));

    await tester.tap(find.byKey(
      const ValueKey('refresh-position-lifecycle-button'),
    ));
    await tester.pumpAndSettle();

    expect(api.lifecycleCalls, 2);
    expect(api.manualSubmitCalls, 0);
    expect(api.guardedSellCalls, 0);

    controller.dispose();
  });
}

void _setLargeViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 1800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _LifecycleApiClient extends ApiClient {
  _LifecycleApiClient({this.realizedMissing = false});

  final bool realizedMissing;
  int lifecycleCalls = 0;
  int manualSubmitCalls = 0;
  int guardedSellCalls = 0;

  @override
  Future<PositionLifecycle> fetchPositionLifecycle({
    String? symbol,
    String provider = 'kis',
    String market = 'KR',
    String status = 'all',
    int limit = 50,
    bool includeEvents = true,
  }) async {
    lifecycleCalls += 1;
    return PositionLifecycle.fromJson(
      positionLifecycleJson(realizedMissing: realizedMissing),
    );
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
    throw StateError('lifecycle panel must not submit manual orders');
  }

  @override
  Future<GuardedPositionSellResult> runGuardedPositionSell({
    required String symbol,
    String provider = 'kis',
    String market = 'KR',
    String quantityMode = 'full',
    double? quantity,
    required bool confirmLive,
    String? clientRequestId,
    String language = 'ko',
    String locale = 'ko-KR',
    String? preflightId,
    String reason = 'manual_exit',
  }) async {
    guardedSellCalls += 1;
    throw StateError('lifecycle panel must not execute guarded sell');
  }
}
