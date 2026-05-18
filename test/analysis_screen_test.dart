import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/analysis/analysis_screen.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/manual_order_screen.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/manual_trading_run_section.dart';
import 'package:auto_invest_dashboard/models/kis_buy_shadow_decision.dart';
import 'package:auto_invest_dashboard/models/kis_limited_auto_buy.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/manual_trading_run_result.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';

void main() {
  testWidgets('Analysis is read-only and sends execution to Trading',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Decision Summary'), findsOneWidget);
    expect(find.text('No single-symbol decision yet. Run one from Trading.'),
        findsOneWidget);
    expect(find.text('Run Single Symbol'), findsNothing);
    expect(find.text('KIS Guarded Trading Run Once'), findsNothing);
    expect(find.text('Submit Live KIS Order'), findsNothing);
    expect(find.text('Watchlist Advanced Details'), findsNothing);
    expect(api.singleRunCalls, 0);

    controller.dispose();
  });

  testWidgets('Trading exposes only KIS Analyze & Buy for KIS selection',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi();
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
      ..selectedProvider = SelectedProvider.kis
      ..selectedPortfolioMarket = PortfolioMarket.kr
      ..selectedWatchlistMarket = PortfolioMarket.kr
      ..selectedOrderMarket = PortfolioMarket.kr
      ..kisLiveConfirmation = true
      ..orderValidationResult = _validationResult()
      ..orderValidationError = 'old validation';

    await tester.pumpWidget(_wrapTrading(controller));

    expect(find.text('KIS Analyze & Buy'), findsOneWidget);
    expect(find.text('KIS Guarded Trading'), findsNothing);
    expect(find.text('KIS Analysis Preview'), findsNothing);
    expect(find.text('KIS Guarded Check Result'), findsNothing);
    expect(find.text('KIS Live Guarded Run Result'), findsNothing);
    expect(find.text('KIS Live Manual Order'), findsNothing);
    expect(find.text('실제 KIS 주문이 제출될 수 있음을 확인했습니다.'), findsOneWidget);
    expect(find.text('Analyze & Buy KIS'), findsOneWidget);
    expect(_filledButtonEnabled(tester, 'Analyze & Buy KIS'), isFalse);
    expect(api.singleRunCalls, 0);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.selectedOrderMarket, PortfolioMarket.kr);

    controller.dispose();
  });

  testWidgets('KIS Analyze & Buy requires checkbox before final dialog',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(_wrapTrading(controller));

    expect(_filledButtonEnabled(tester, 'Analyze & Buy KIS'), isFalse);
    expect(find.text('실제 KIS 주문이 제출될 수 있음을 확인했습니다.'), findsOneWidget);
    await tester.tap(find.text('Analyze & Buy KIS'));
    await tester.pumpAndSettle();

    expect(api.kisBuyShadowCalls, 0);
    expect(api.kisLimitedAutoBuyCalls, 0);
    expect(find.text('Confirm KIS Order'), findsNothing);

    controller.dispose();
  });

  testWidgets('KIS Analyze & Buy uses one checkbox and final dialog',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..kisSafetyStatus = const KisManualOrderSafetyStatus(
        runtimeDryRun: false,
        killSwitch: false,
        kisEnabled: true,
        kisRealOrderEnabled: true,
        marketOpen: true,
        entryAllowedNow: true,
        noNewEntryAfter: '15:00',
      );

    await tester.pumpWidget(_wrapTrading(controller));

    expect(_filledButtonEnabled(tester, 'Analyze & Buy KIS'), isFalse);
    await tester.tap(find.text('실제 KIS 주문이 제출될 수 있음을 확인했습니다.'));
    await tester.pumpAndSettle();

    expect(_filledButtonEnabled(tester, 'Analyze & Buy KIS'), isTrue);
    await tester.tap(find.text('Analyze & Buy KIS'));
    await tester.pumpAndSettle();

    expect(find.text('Confirm KIS Order'), findsWidgets);
    expect(api.kisLimitedAutoBuyCalls, 0);

    controller.dispose();
  });

  testWidgets('Analysis score breakdown renders realistic payload values',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi(realisticScores: true);
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(_wrapTrading(controller));
    await tester.enterText(find.widgetWithText(TextField, 'Symbol'), 'aapl');
    await tester.tap(find.text('Analyze & Paper Buy'));
    await tester.pumpAndSettle();

    expect(find.text('Score Breakdown'), findsOneWidget);
    expect(find.text('BUY SCORE'), findsOneWidget);
    expect(find.text('65.00'), findsOneWidget);
    expect(find.text('SELL SCORE'), findsOneWidget);
    expect(find.text('12.00'), findsOneWidget);
    expect(find.text('AI BUY'), findsOneWidget);
    expect(find.text('71.00'), findsOneWidget);
    expect(find.text('AI SELL'), findsOneWidget);
    expect(find.text('22.00'), findsOneWidget);
    expect(find.text('FINAL BUY'), findsOneWidget);
    expect(find.text('69.00'), findsOneWidget);
    expect(find.text('FINAL SELL'), findsOneWidget);
    expect(find.text('18.00'), findsOneWidget);
    expect(find.text('CONFIDENCE'), findsOneWidget);
    expect(find.text('0.77'), findsOneWidget);
    expect(find.text('ACTION'), findsOneWidget);
    expect(find.text('REASON'), findsOneWidget);
    expect(find.text('N/A'), findsNothing);
    expect(find.text('Run Details'), findsOneWidget);
    expect(find.text('Indicator Details'), findsNothing);

    controller.dispose();
  });

  testWidgets('Single Symbol score breakdown enriches from matching signal id',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi(signalIdOnly: true);
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(_wrapTrading(controller));
    await tester.enterText(find.widgetWithText(TextField, 'Symbol'), 'aapl');
    await tester.tap(find.text('Analyze & Paper Buy'));
    await tester.pumpAndSettle();

    expect(api.signalFetchCalls, 1);
    expect(find.text('BUY SCORE'), findsOneWidget);
    expect(find.text('62.00'), findsOneWidget);
    expect(find.text('SELL SCORE'), findsOneWidget);
    expect(find.text('13.00'), findsOneWidget);
    expect(find.text('FINAL BUY'), findsOneWidget);
    expect(find.text('67.00'), findsOneWidget);
    expect(find.text('FINAL SELL'), findsOneWidget);
    expect(find.text('11.00'), findsOneWidget);
    expect(find.text('CONFIDENCE'), findsOneWidget);
    expect(find.text('0.74'), findsOneWidget);
    expect(find.text('Score below entry threshold'), findsWidgets);
    expect(find.text('recent signal reason'), findsWidgets);
    expect(find.text('N/A'), findsNothing);

    controller.dispose();
  });

  testWidgets('Single Symbol immediate-only fallback is explicit',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi(signalIdOnly: true, failSignalFetch: true);
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(_wrapTrading(controller));
    await tester.tap(find.text('Analyze & Paper Buy'));
    await tester.pumpAndSettle();

    expect(find.text('Score details not returned in run response'),
        findsOneWidget);
    expect(find.text('No numeric GPT score returned'), findsNWidgets(2));
    expect(find.text('GPT Advisory Reason'), findsOneWidget);
    expect(find.text('Immediate GPT context says risk is elevated.'),
        findsOneWidget);
    expect(find.text('N/A'), findsNothing);

    controller.dispose();
  });

  testWidgets('Analysis score breakdown uses explicit fallback only for nulls',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false);
    controller.manualRunResult = ManualTradingRunResult.fromJson({
      'symbol': 'AAPL',
      'gate_level': 2,
      'action': 'hold',
      'result': 'skipped',
      'reason': 'No actionable edge',
      'buy_score': 61,
      'ai_buy_score': null,
      'final_buy_score': 60,
      'confidence': null,
    });

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: ManualTradingRunSection(controller: controller),
        ),
      ),
    ));

    expect(find.text('BUY SCORE'), findsOneWidget);
    expect(find.text('61.00'), findsOneWidget);
    expect(find.text('FINAL BUY'), findsOneWidget);
    expect(find.text('60.00'), findsOneWidget);
    expect(find.text('--'), findsWidgets);
    expect(find.text('N/A'), findsNothing);

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

Widget _wrapTrading(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: TradingScreen(controller: controller),
    ),
  );
}

bool _filledButtonEnabled(WidgetTester tester, String label) {
  final button = tester.widget<ButtonStyleButton>(
    find
        .ancestor(
          of: find.text(label),
          matching: find.byWidgetPredicate(
            (widget) => widget is ButtonStyleButton,
          ),
        )
        .first,
  );
  return button.onPressed != null;
}

class _AnalysisFakeApi extends ApiClient {
  _AnalysisFakeApi({
    this.realisticScores = false,
    this.signalIdOnly = false,
    this.failSignalFetch = false,
  });

  final bool realisticScores;
  final bool signalIdOnly;
  final bool failSignalFetch;
  int singleRunCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;
  int signalFetchCalls = 0;
  int kisBuyShadowCalls = 0;
  int kisLimitedAutoBuyCalls = 0;
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
    if (signalIdOnly) {
      return ManualTradingRunResult.fromJson({
        'symbol': symbol,
        'gate_level': gateLevel,
        'signal_id': 42,
        'action': 'hold',
        'result': 'skipped',
        'reason': 'Immediate response omitted score details',
        'hard_block_reason': 'market_closed',
        'gpt_context': {
          'reason': 'Immediate GPT context says risk is elevated.',
          'gpt_buy_score': null,
          'gpt_sell_score': null,
        },
      });
    }
    if (realisticScores) {
      return ManualTradingRunResult.fromJson({
        'symbol': symbol,
        'gate_level': gateLevel,
        'response_payload': {
          'symbol': symbol,
          'action': 'hold',
          'reason': 'Scores available but entry gate blocked',
          'signal_status': 'skipped',
          'scores': {
            'buy_score': 65,
            'sell_score': 12,
            'quant_buy_score': '66',
            'quant_sell_score': 14,
            'ai_buy_score': 71,
            'ai_sell_score': '22',
            'final_buy_score': 69,
            'final_sell_score': 18,
            'confidence': '0.77',
          },
          'indicator_payload': {'rsi': 55.4},
        },
        'result': 'skipped',
      });
    }
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
  Future<List<Map<String, dynamic>>> fetchRecentSignalPayloads({
    int limit = 20,
  }) async {
    signalFetchCalls += 1;
    if (failSignalFetch) {
      throw const ApiRequestException('signals unavailable');
    }
    return [
      {
        'id': 42,
        'symbol': 'AAPL',
        'action': 'hold',
        'signal_status': 'skipped',
        'buy_score': 62,
        'sell_score': 13,
        'final_buy_score': 67,
        'final_sell_score': 11,
        'confidence': 0.74,
        'reason': 'recent signal reason',
        'risk_flags': ['hold_signal'],
        'gating_notes': ['score_threshold_not_met'],
        'gpt_context': {
          'reason': 'recent signal reason',
          'gpt_buy_score': null,
          'gpt_sell_score': null,
        },
      },
    ];
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

  @override
  Future<KisBuyShadowDecision> runKisBuyShadowOnce() async {
    kisBuyShadowCalls += 1;
    return KisBuyShadowDecision.fromJson({
      'status': 'ok',
      'mode': 'shadow_buy_dry_run',
      'decision': 'blocked',
      'action': 'hold',
      'reason': 'market_closed',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'checks': {'market_open': false},
      'safety': {
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      },
    });
  }

  @override
  Future<KisLimitedAutoBuy> runKisLimitedAutoBuyOnce({int? gateLevel}) async {
    kisLimitedAutoBuyCalls += 1;
    return KisLimitedAutoBuy.fromJson({
      'status': 'ok',
      'mode': 'limited_auto_buy',
      'result': 'blocked',
      'action': 'hold',
      'reason': 'market_closed',
      'symbol': '005930',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'checks': {'market_open': false},
      'safety': {'preview_only': false},
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
