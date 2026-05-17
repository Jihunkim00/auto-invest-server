import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/analysis/analysis_screen.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/manual_trading_run_result.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';

void main() {
  testWidgets('Analysis restores Single Symbol Trading for Alpaca Paper',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Single Symbol Trading'), findsOneWidget);
    expect(find.text('Alpaca Paper / US'), findsOneWidget);
    expect(find.text('KIS / KR'), findsOneWidget);
    expect(find.text('Symbol selector'), findsOneWidget);
    expect(find.text('Symbol'), findsOneWidget);
    expect(find.text('Gate 1'), findsOneWidget);
    expect(find.text('Gate 2'), findsOneWidget);
    expect(find.text('Gate 3'), findsOneWidget);
    expect(find.text('Gate 4'), findsOneWidget);
    expect(find.text('Run Single Symbol'), findsOneWidget);
    expect(find.text('Uses existing risk engine'), findsOneWidget);
    expect(find.text('Paper order may be created if risk-approved'),
        findsOneWidget);
    expect(find.text('HOLD is normal'), findsOneWidget);

    await tester.ensureVisible(find.text('Gate 3'));
    await tester.tap(find.text('Gate 3'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Symbol'), 'msft');
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Run Single Symbol'));
    await tester.tap(find.text('Run Single Symbol'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Continue'));
    await tester.pumpAndSettle();

    expect(api.singleRunCalls, 1);
    expect(api.lastSingleRunSymbol, 'MSFT');
    expect(api.lastSingleRunGateLevel, 3);
    expect(find.text('Result Summary'), findsOneWidget);
    expect(find.text('HOLD'), findsWidgets);
    expect(find.text('skipped'), findsWidgets);
    expect(find.text('Why No Trade?'), findsOneWidget);
    expect(find.text('Score Breakdown'), findsOneWidget);
    expect(find.text('QUANT SCORE'), findsOneWidget);
    expect(find.text('AI SCORE'), findsOneWidget);
    expect(find.text('FINAL SCORE'), findsOneWidget);
    expect(find.text('No order created.'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('KIS single symbol path only prepares Manual Order ticket',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi();
    var openedManualOrder = false;
    final controller = DashboardController(api, autoload: false)
      ..krWatchlist = const MarketWatchlist(
        market: 'KR',
        currency: 'KRW',
        timezone: 'Asia/Seoul',
        watchlistFile: 'config/watchlist_kr.yaml',
        count: 1,
        symbols: [
          WatchlistSymbol(
            symbol: '005930',
            name: 'Samsung Electronics',
            market: 'KOSPI',
          ),
        ],
      )
      ..kisLiveConfirmation = true
      ..orderValidationResult = _validationResult()
      ..orderValidationError = 'old validation';

    await tester.pumpWidget(_wrap(
      controller,
      onOpenManualOrder: () => openedManualOrder = true,
    ));

    await tester.tap(find.text('KIS / KR'));
    await tester.pumpAndSettle();

    expect(find.text('Prepare Buy Ticket'), findsOneWidget);
    expect(find.text('Manual Order only'), findsOneWidget);
    expect(find.text('No KIS live submit here'), findsOneWidget);
    expect(find.text('confirm_live remains unchecked'), findsOneWidget);
    expect(find.text('Submit Live KIS Order'), findsNothing);
    expect(find.text('Run Single Symbol'), findsNothing);

    await tester.enterText(find.widgetWithText(TextField, 'Symbol'), '005930');
    await tester.ensureVisible(find.text('Prepare Buy Ticket'));
    await tester.tap(find.text('Prepare Buy Ticket'));
    await tester.pumpAndSettle();

    expect(openedManualOrder, isTrue);
    expect(api.singleRunCalls, 0);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.selectedOrderMarket, PortfolioMarket.kr);
    expect(controller.orderTicketSymbol, '005930');
    expect(controller.orderTicketSide, 'buy');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(controller.orderValidationError, isNull);
    expect(
      controller.orderTicketSourceMetadata?['source'],
      'single_symbol_trading',
    );
    expect(find.text('Result Summary'), findsOneWidget);
    expect(find.text('No order created'), findsOneWidget);

    controller.dispose();
  });
}

Widget _wrap(
  DashboardController controller, {
  VoidCallback? onOpenManualOrder,
}) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: AnalysisScreen(
        controller: controller,
        onOpenManualOrder: onOpenManualOrder,
      ),
    ),
  );
}

class _AnalysisFakeApi extends ApiClient {
  int singleRunCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;
  String? lastSingleRunSymbol;
  int? lastSingleRunGateLevel;

  @override
  Future<ManualTradingRunResult> runTradingOnce({
    required String symbol,
    required int gateLevel,
  }) async {
    singleRunCalls += 1;
    lastSingleRunSymbol = symbol;
    lastSingleRunGateLevel = gateLevel;
    return ManualTradingRunResult.fromJson({
      'symbol': symbol,
      'gate_level': gateLevel,
      'action': 'hold',
      'result': 'skipped',
      'signal_status': 'skipped',
      'reason': 'signal action is HOLD; execution skipped',
      'approved_by_risk': false,
      'risk_flags': ['hold_signal'],
      'gating_notes': ['score_threshold_not_met'],
      'quant_buy_score': 61,
      'ai_buy_score': 59,
      'final_buy_score': 60,
      'confidence': 0.62,
    });
  }

  @override
  Future<OrderValidationResult> validateKisOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    Map<String, dynamic>? sourceMetadata,
  }) async {
    validationCalls += 1;
    return _validationResult();
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
    return KisManualOrderResult.fromJson({
      'order_id': 1,
      'symbol': symbol,
      'side': side,
      'qty': qty,
      'internal_status': 'SUBMITTED',
      'created_at': '2026-05-17T00:00:00',
      'updated_at': '2026-05-17T00:00:00',
    });
  }
}

OrderValidationResult _validationResult() {
  return const OrderValidationResult(
    provider: 'kis',
    market: 'KR',
    environment: 'prod',
    dryRun: true,
    validatedForSubmission: true,
    canSubmitLater: true,
    symbol: '005930',
    side: 'buy',
    qty: 1,
    orderType: 'market',
    currentPrice: 72000,
    estimatedAmount: 72000,
    availableCash: 1000000,
    heldQty: null,
    warnings: [],
    blockReasons: [],
    marketSession: MarketSessionStatus(
      market: 'KR',
      timezone: 'Asia/Seoul',
      isMarketOpen: true,
      isEntryAllowedNow: true,
      isNearClose: false,
    ),
    orderPreview: OrderPreview(
      accountNoMasked: '12****78',
      productCode: '01',
      symbol: '005930',
      side: 'buy',
      qty: 1,
      orderType: 'market',
      kisTrIdPreview: 'TTTC0802U',
      payloadPreview: {'CANO': '12****78', 'PDNO': '005930'},
    ),
  );
}
