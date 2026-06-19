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
import 'package:auto_invest_dashboard/models/kis_single_symbol_trading_result.dart';
import 'package:auto_invest_dashboard/models/manual_trading_run_result.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';
import 'package:auto_invest_dashboard/models/watchlist_run_result.dart';

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

    expect(find.text('No KIS watchlist summary yet.'), findsOneWidget);
    expect(
      find.text('Run KIS Watchlist Preview from Dashboard first.'),
      findsOneWidget,
    );
    expect(find.text('Run Single Symbol'), findsNothing);
    expect(find.text('KIS Guarded Trading Run Once'), findsNothing);
    expect(find.text('Submit Live KIS Order'), findsNothing);
    expect(find.text('Watchlist Advanced Details'), findsNothing);
    expect(api.singleRunCalls, 0);

    controller.dispose();
  });

  testWidgets(
      'Trading exposes Single Symbol Analyze & Buy and KIS manual ticket',
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

    expect(find.text('Analyze Selected Symbol'), findsWidgets);
    expect(find.text('Validate Manual Order'), findsWidgets);
    expect(find.text('Submit Live Order'), findsWidgets);
    expect(find.text('KIS Manual Buy/Sell Ticket'), findsOneWidget);
    expect(find.text('Buy'), findsOneWidget);
    expect(find.text('Sell'), findsOneWidget);
    expect(find.text('KIS Guarded Trading'), findsNothing);
    expect(find.text('KIS Analysis Preview'), findsNothing);
    expect(find.text('KIS Guarded Check Result'), findsNothing);
    expect(find.text('KIS Live Guarded Run Result'), findsNothing);
    expect(find.text('Watchlist Analyze & Buy'), findsNothing);
    expect(find.text('Position Management'), findsNothing);
    expect(find.text('Scheduled Position Management'), findsNothing);
    expect(find.text('KIS Scheduler Guarded Buy'), findsNothing);
    expect(find.text('KIS Scheduler Guarded Sell'), findsNothing);
    expect(
      find.text(
        'I understand Submit Live Order requires confirm_live and final confirmation.',
      ),
      findsOneWidget,
    );
    expect(
      find.textContaining('Analysis does not submit an order.'),
      findsOneWidget,
    );
    expect(_filledButtonEnabled(tester, 'Submit Live Order'), isFalse);
    expect(api.singleRunCalls, 0);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.selectedOrderMarket, PortfolioMarket.kr);

    controller.dispose();
  });

  testWidgets(
      'Single Symbol Analyze & Buy requires checkbox before final dialog',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(_wrapTrading(controller));

    expect(
      find.widgetWithText(
        CheckboxListTile,
        'I understand Submit Live Order requires confirm_live and final confirmation.',
      ),
      findsOneWidget,
    );
    expect(_filledButtonEnabled(tester, 'Submit Live Order'), isFalse);
    expect(
      find.text(
        'I understand Submit Live Order requires confirm_live and final confirmation.',
      ),
      findsOneWidget,
    );
    await tester
        .tap(find.byKey(const Key('kis_trading_analyze_submit_button')));
    await tester.pumpAndSettle();

    expect(api.kisBuyShadowCalls, 0);
    expect(api.kisLimitedAutoBuyCalls, 0);
    expect(api.kisSingleSymbolCalls, 0);
    expect(find.text('Submit Live Order'), findsWidgets);

    controller.dispose();
  });

  testWidgets('KIS Analyze button calls analysis-only endpoint',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(_wrapTrading(controller));

    await tester.tap(find.byKey(const Key('kis_trading_analyze_button')));
    await tester.pumpAndSettle();

    expect(api.kisSingleSymbolCalls, 1);
    expect(api.lastKisSingleSymbol, '005930');
    expect(api.lastKisSingleQuantity, isNull);
    expect(api.lastKisSingleConfirmLive, isFalse);
    expect(api.lastKisSingleRequestedAction, 'analyze_only');

    controller.dispose();
  });

  testWidgets('KIS Validate Manual Order does not submit or analyze',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(_wrapTrading(controller));

    await tester.tap(find.byKey(const Key('kis_trading_validate_button')));
    await tester.pumpAndSettle();

    expect(api.validationCalls, 1);
    expect(api.kisSingleSymbolCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.text('Manual order validated. No order submitted.'),
        findsOneWidget);

    controller.dispose();
  });

  testWidgets('Single Symbol Analyze & Buy uses one checkbox and final dialog',
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

    expect(_filledButtonEnabled(tester, 'Submit Live Order'), isFalse);
    await tester.tap(find.text(
      'I understand Submit Live Order requires confirm_live and final confirmation.',
    ));
    await tester.pumpAndSettle();

    expect(_filledButtonEnabled(tester, 'Submit Live Order'), isTrue);
    await tester
        .tap(find.byKey(const Key('kis_trading_analyze_submit_button')));
    await tester.pumpAndSettle();

    expect(find.text('Submit Live Order'), findsWidgets);
    expect(api.kisLimitedAutoBuyCalls, 0);
    expect(api.kisSingleSymbolCalls, 0);

    await _tapFinalSubmitLiveOrderDialog(tester);
    await tester.pumpAndSettle();

    expect(api.kisSingleSymbolCalls, 1);
    expect(api.lastKisSingleSymbol, '005930');
    expect(api.lastKisSingleQuantity, 1);
    expect(api.lastKisSingleConfirmLive, isTrue);
    expect(find.text('Analysis Status'), findsWidgets);

    controller.dispose();
  });

  testWidgets(
      'Single Symbol Analyze & Buy renders dry-run and score-missing results',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi(
      kisSingleResult: KisSingleSymbolTradingResult.fromJson({
        'status': 'ok',
        'mode': 'kis_single_symbol_analyze_buy',
        'symbol': '005930',
        'requested_symbol': '005930',
        'analyzed_symbol': '005930',
        'symbol_match': true,
        'action': 'buy',
        'result': 'dry_run',
        'reason': 'dry_run_mode',
        'quantity': 1,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'dry_run': true,
        'safety': {'dry_run': true},
      }),
    );
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(_wrapTrading(controller));
    await tester.tap(find.text(
      'I understand Submit Live Order requires confirm_live and final confirmation.',
    ));
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const Key('kis_trading_analyze_submit_button')));
    await tester.pumpAndSettle();
    await _tapFinalSubmitLiveOrderDialog(tester);
    await tester.pumpAndSettle();

    expect(find.textContaining('Dry-run'), findsWidgets);
    expect(find.text('Analysis unavailable'), findsOneWidget);
    expect(find.text('KIS OHLCV data was not available'), findsWidgets);
    expect(find.text('N/A'), findsNothing);

    controller.dispose();
  });

  testWidgets(
      'Single Symbol Analyze & Buy warns when returned symbol mismatches',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi(
      kisSingleResult: KisSingleSymbolTradingResult.fromJson({
        'status': 'ok',
        'mode': 'kis_single_symbol_analyze_buy',
        'symbol': '005380',
        'requested_symbol': '005380',
        'analyzed_symbol': '005930',
        'returned_symbol': '005930',
        'symbol_match': false,
        'action': 'hold',
        'result': 'blocked',
        'reason': 'symbol_mismatch',
        'quantity': 1,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'safety': {'dry_run': false},
      }),
    );
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(_wrapTrading(controller));
    await tester.enterText(
        find.widgetWithText(TextField, 'KR Symbol'), '005380');
    await tester.tap(find.text(
      'I understand Submit Live Order requires confirm_live and final confirmation.',
    ));
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const Key('kis_trading_analyze_submit_button')));
    await tester.pumpAndSettle();
    await _tapFinalSubmitLiveOrderDialog(tester);
    await tester.pumpAndSettle();

    expect(api.lastKisSingleSymbol, '005380');
    expect(
      find.text(
        'Returned candidate does not match selected symbol. Selected: 005380, Returned: 005930',
      ),
      findsOneWidget,
    );
    expect(
      find.textContaining('Returned candidate does not match selected symbol'),
      findsWidgets,
    );

    controller.dispose();
  });

  testWidgets(
      'Single Symbol Analyze & Buy normalizes completed low-score analysis',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi(
      kisSingleResult: KisSingleSymbolTradingResult.fromJson(
        _kisCompletedAnalysisPayload(
          symbol: '091810',
          finalBuyScore: 12.0,
          finalSellScore: 56.75,
          currentPrice: 856,
          reason: 'buy_entry_not_allowed_now',
          noOrderReason: 'buy_entry_not_allowed_now',
          riskFlags: const [
            'below_EMA20',
            'below_EMA50',
            'below_VWAP',
            'oversold_RSI',
            'negative_momentum',
            'weak_recent_return',
            'near_close_no_new_entry',
            'KR_trading_disabled',
          ],
          indicatorPayload: const {
            'price': 856,
            'close': 856,
            'ema20': 924.110654,
            'ema50': 1011.321289,
            'rsi': 20.982143,
            'vwap': 1078.523265,
            'volume_ratio': 0.708535,
            'momentum': -0.059341,
            'recent_return': -0.14656,
          },
          validationWarnings: const [
            'after_no_new_entry_time',
            'near_close',
          ],
          entryAllowedNow: false,
          nearClose: true,
        ),
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(_wrapTrading(controller));
    await _submitKisAnalyzeBuy(tester, symbol: '091810');

    expect(find.text('Analysis Status'), findsOneWidget);
    expect(find.text('Analysis completed'), findsOneWidget);
    expect(find.text('Analysis unavailable'), findsNothing);
    expect(find.text('Data unavailable'), findsNothing);
    expect(find.text('Score vs Threshold'), findsOneWidget);
    expect(find.text('BUY SCORE'), findsOneWidget);
    expect(find.text('12.0'), findsOneWidget);
    expect(find.text('REQUIRED SCORE'), findsOneWidget);
    expect(find.text('65'), findsOneWidget);
    expect(find.text('Score below entry threshold'), findsWidgets);
    expect(find.textContaining('New buy entries are not allowed now'),
        findsWidgets);
    expect(find.textContaining('New buy entries are blocked after 15:00'),
        findsWidgets);
    expect(find.textContaining('KR_trading_disabled'), findsNothing);
    expect(find.text('Developer Raw Payload'), findsOneWidget);

    controller.dispose();
  });

  testWidgets(
      'Single Symbol Analyze & Buy uses one card structure across KR symbols',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final payloads = [
      _kisCompletedAnalysisPayload(
        symbol: '005380',
        finalBuyScore: 42.25,
        finalSellScore: 28,
        currentPrice: 241000,
        reason: 'score_threshold_not_met',
        noOrderReason: 'score_threshold_not_met',
        riskFlags: const ['overbought_RSI', 'chase_risk'],
        indicatorPayload: const {
          'price': 241000,
          'close': 241000,
          'ema20': 220000,
          'ema50': 214000,
          'vwap': 226000,
          'rsi': 76.4,
          'volume_ratio': 1.34,
          'momentum': 0.041,
          'recent_return': 0.082,
        },
      ),
      _kisCompletedAnalysisPayload(
        symbol: '005930',
        finalBuyScore: 68,
        finalSellScore: 18,
        currentPrice: 72000,
        reason: 'hold_signal',
        noOrderReason: 'hold_signal',
        riskFlags: const [],
        indicatorPayload: const {
          'price': 72000,
          'close': 72000,
          'ema20': 71000,
          'ema50': 70500,
          'vwap': 71500,
          'rsi': 54,
          'volume_ratio': 1.02,
          'momentum': 0.006,
          'recent_return': 0.012,
        },
      ),
      _kisCompletedAnalysisPayload(
        symbol: '091810',
        finalBuyScore: 12,
        finalSellScore: 56.75,
        currentPrice: 856,
        reason: 'buy_entry_not_allowed_now',
        noOrderReason: 'buy_entry_not_allowed_now',
        riskFlags: const ['below_EMA20', 'below_EMA50', 'below_VWAP'],
        indicatorPayload: const {
          'price': 856,
          'close': 856,
          'ema20': 924.110654,
          'ema50': 1011.321289,
          'vwap': 1078.523265,
          'rsi': 20.982143,
          'volume_ratio': 0.708535,
          'momentum': -0.059341,
          'recent_return': -0.14656,
        },
      ),
    ];

    for (final payload in payloads) {
      final symbol = payload['symbol']!.toString();
      final api = _AnalysisFakeApi(
        kisSingleResult: KisSingleSymbolTradingResult.fromJson(payload),
      );
      final controller = DashboardController(api, autoload: false)
        ..selectedProvider = SelectedProvider.kis;

      await tester.pumpWidget(_wrapTrading(controller));
      await _submitKisAnalyzeBuy(tester, symbol: symbol);

      _expectKisNormalizedSections();
      expect(find.text('Analysis completed'), findsOneWidget);
      expect(find.text('BUY SCORE'), findsOneWidget);
      expect(find.text('REQUIRED SCORE'), findsOneWidget);
      expect(find.text('Developer Raw Payload'), findsOneWidget);

      controller.dispose();
    }
  });

  testWidgets('Single Symbol Analyze & Buy keeps raw reason inside raw payload',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi(
      kisSingleResult: KisSingleSymbolTradingResult.fromJson(
        _kisCompletedAnalysisPayload(
          symbol: '091810',
          finalBuyScore: 12,
          finalSellScore: 56.75,
          currentPrice: 856,
          reason: 'buy_entry_not_allowed_now',
          noOrderReason: 'buy_entry_not_allowed_now',
          riskFlags: const ['KR_trading_disabled'],
          indicatorPayload: const {
            'price': 856,
            'close': 856,
            'ema20': 924.110654,
            'ema50': 1011.321289,
            'vwap': 1078.523265,
            'rsi': 20.982143,
            'volume_ratio': 0.708535,
            'momentum': -0.059341,
            'recent_return': -0.14656,
          },
        ),
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(_wrapTrading(controller));
    await _submitKisAnalyzeBuy(tester, symbol: '091810');

    expect(find.textContaining('KIS trading is disabled'), findsWidgets);
    expect(find.textContaining('KR_trading_disabled'), findsNothing);

    await tester.ensureVisible(find.text('Developer Raw Payload'));
    await tester.tap(find.text('Developer Raw Payload'));
    await tester.pumpAndSettle();

    expect(find.textContaining('KR_trading_disabled'), findsOneWidget);

    controller.dispose();
  });

  testWidgets(
      'Single Symbol Analyze & Buy does not fall back to watchlist top candidate',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi(
      kisSingleResult: KisSingleSymbolTradingResult.fromJson(
        _kisCompletedAnalysisPayload(
          symbol: '091810',
          finalBuyScore: 12,
          finalSellScore: 56.75,
          currentPrice: 856,
          reason: 'score_threshold_not_met',
          noOrderReason: 'score_threshold_not_met',
          riskFlags: const [],
          indicatorPayload: const {
            'price': 856,
            'close': 856,
            'ema20': 924,
            'ema50': 1011,
            'vwap': 1078,
            'rsi': 21,
            'volume_ratio': 0.7,
            'momentum': -0.05,
            'recent_return': -0.14,
          },
        ),
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..runResult = WatchlistRunResult.fromJson({
        'final_best_candidate': {
          'symbol': '005930',
          'final_entry_score': 90,
          'final_buy_score': 90,
          'entry_ready': true,
          'action_hint': 'buy',
        },
        'final_ranked_candidates': [
          {'symbol': '005930', 'final_entry_score': 90}
        ],
      });

    await tester.pumpWidget(_wrapTrading(controller));
    await _submitKisAnalyzeBuy(tester, symbol: '091810');

    expect(api.lastKisSingleSymbol, '091810');
    expect(find.text('091810'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Single Symbol Analyze & Buy shows insufficient cash amounts',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _AnalysisFakeApi(
      kisSingleResult: KisSingleSymbolTradingResult.fromJson(
        _kisCompletedAnalysisPayload(
          symbol: '005930',
          finalBuyScore: 37,
          finalSellScore: 21,
          currentPrice: 56700,
          reason: 'insufficient_cash',
          noOrderReason: 'insufficient_cash',
          riskFlags: const ['insufficient_cash'],
          indicatorPayload: const {
            'price': 56700,
            'close': 56700,
            'ema20': 54000,
            'ema50': 53200,
            'vwap': 54800,
            'rsi': 73,
            'volume_ratio': 1.2,
            'momentum': -0.01,
            'recent_return': 0.06,
          },
          validationBlockReasons: const ['insufficient_cash'],
          estimatedAmount: 283500,
          availableCash: 20168,
        ),
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(_wrapTrading(controller));
    await _submitKisAnalyzeBuy(tester, symbol: '005930');

    expect(find.text('Cash Check'), findsOneWidget);
    expect(find.text('AVAILABLE CASH'), findsOneWidget);
    expect(find.text('\u20A920,168'), findsOneWidget);
    expect(find.text('ESTIMATED AMOUNT'), findsOneWidget);
    expect(find.text('\u20A9283,500'), findsOneWidget);
    expect(find.text('CASH SHORTFALL'), findsOneWidget);
    expect(find.text('\u20A9263,332'), findsOneWidget);
    expect(find.text('Available cash is below estimated order amount'),
        findsWidgets);

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

Future<void> _submitKisAnalyzeBuy(
  WidgetTester tester, {
  String symbol = '005930',
}) async {
  await tester.enterText(find.widgetWithText(TextField, 'KR Symbol'), symbol);
  await tester.tap(find.widgetWithText(
    CheckboxListTile,
    'I understand Submit Live Order requires confirm_live and final confirmation.',
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('kis_trading_analyze_submit_button')));
  await tester.pumpAndSettle();
  await _tapFinalSubmitLiveOrderDialog(tester);
  await tester.pumpAndSettle();
}

Future<void> _tapFinalSubmitLiveOrderDialog(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(FilledButton, 'Submit Live Order').last);
}

void _expectKisNormalizedSections() {
  expect(find.text('Analysis Status'), findsOneWidget);
  expect(find.text('Score vs Threshold'), findsOneWidget);
  expect(find.text('Main Reason'), findsOneWidget);
  expect(find.text('Technical Snapshot'), findsOneWidget);
  expect(find.text('Why No Order?'), findsOneWidget);
  expect(find.text('Order Submission'), findsOneWidget);
  expect(find.text('Developer Raw Payload'), findsOneWidget);
}

class _AnalysisFakeApi extends ApiClient {
  _AnalysisFakeApi({
    this.realisticScores = false,
    this.signalIdOnly = false,
    this.failSignalFetch = false,
    KisSingleSymbolTradingResult? kisSingleResult,
  }) : kisSingleResult = kisSingleResult ?? _kisSingleResult();

  final bool realisticScores;
  final bool signalIdOnly;
  final bool failSignalFetch;
  KisSingleSymbolTradingResult kisSingleResult;
  int singleRunCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;
  int signalFetchCalls = 0;
  int kisBuyShadowCalls = 0;
  int kisLimitedAutoBuyCalls = 0;
  int kisSingleSymbolCalls = 0;
  String? lastSingleRunSymbol;
  int? lastSingleRunGateLevel;
  String? lastKisSingleSymbol;
  int? lastKisSingleGateLevel;
  int? lastKisSingleQuantity;
  bool? lastKisSingleConfirmLive;
  String? lastKisSingleRequestedAction;
  Map<String, dynamic>? lastKisSingleSourceContext;

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async {
    return const KisManualOrderSafetyStatus(
      runtimeDryRun: false,
      killSwitch: false,
      kisEnabled: true,
      kisRealOrderEnabled: true,
      marketOpen: true,
      entryAllowedNow: true,
      noNewEntryAfter: '15:00',
    );
  }

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

  @override
  Future<KisSingleSymbolTradingResult> runKisSingleSymbolAnalyzeBuy({
    required String symbol,
    int? gateLevel,
    int? quantity,
    double? amount,
    required bool confirmLive,
    bool? dryRun,
    String requestedAction = 'analyze_then_maybe_buy',
    String sourceEndpoint = 'flutter_trading',
    Map<String, dynamic>? sourceContext,
  }) async {
    kisSingleSymbolCalls += 1;
    lastKisSingleSymbol = symbol;
    lastKisSingleGateLevel = gateLevel;
    lastKisSingleQuantity = quantity;
    lastKisSingleConfirmLive = confirmLive;
    lastKisSingleRequestedAction = requestedAction;
    lastKisSingleSourceContext = sourceContext;
    return kisSingleResult;
  }

  @override
  Future<List<TradingRun>> getRecentTradingRuns() async => const [];

  @override
  Future<PortfolioSummary> fetchPortfolioSummary() async =>
      PortfolioSummary.empty();

  @override
  Future<PortfolioSummary> fetchUsPortfolioSummary() async =>
      PortfolioSummary.empty();

  @override
  Future<PortfolioSummary> fetchKrPortfolioSummary() async =>
      PortfolioSummary.empty(currency: 'KRW');
}

KisSingleSymbolTradingResult _kisSingleResult() {
  return KisSingleSymbolTradingResult.fromJson({
    'status': 'ok',
    'mode': 'kis_single_symbol_analyze_buy',
    'symbol': '005930',
    'requested_symbol': '005930',
    'analyzed_symbol': '005930',
    'symbol_match': true,
    'action': 'buy',
    'result': 'dry_run',
    'reason': 'dry_run_mode',
    'quantity': 1,
    'primary_score': 82,
    'final_buy_score': 82,
    'final_sell_score': 8,
    'quant_buy_score': 80,
    'quant_sell_score': 10,
    'ai_buy_score': 84,
    'ai_sell_score': 7,
    'gpt_buy_score': 84,
    'gpt_sell_score': 7,
    'confidence': 0.8,
    'gpt_reason': 'single symbol advisory',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'dry_run': true,
    'safety': {'dry_run': true},
  });
}

Map<String, dynamic> _kisCompletedAnalysisPayload({
  required String symbol,
  required double finalBuyScore,
  required double finalSellScore,
  required double currentPrice,
  required String reason,
  required String noOrderReason,
  required List<String> riskFlags,
  required Map<String, dynamic> indicatorPayload,
  List<String> validationWarnings = const [],
  List<String> validationBlockReasons = const [],
  double? estimatedAmount,
  double? availableCash,
  bool entryAllowedNow = true,
  bool nearClose = false,
}) {
  return {
    'status': 'ok',
    'mode': 'kis_single_symbol_analyze_buy',
    'symbol': symbol,
    'requested_symbol': symbol,
    'analyzed_symbol': symbol,
    'returned_symbol': symbol,
    'symbol_match': true,
    'action': 'hold',
    'result':
        noOrderReason == 'buy_entry_not_allowed_now' ? 'blocked' : 'skipped',
    'reason': reason,
    'quantity': 1,
    'current_price': currentPrice,
    'primary_score': finalBuyScore,
    'final_entry_score': finalBuyScore,
    'final_buy_score': finalBuyScore,
    'final_sell_score': finalSellScore,
    'confidence': 0.77,
    'gpt_reason': _mojibakeFallbackReason(),
    'risk_flags': riskFlags,
    'gating_notes': const ['KIS OHLCV indicators were used for quant scoring.'],
    'block_reason': noOrderReason,
    'no_order_reason': noOrderReason,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'dry_run': false,
    'order_status': 'No order created',
    'safety': {
      'dry_run': false,
      'runtime_dry_run': false,
      'entry_allowed_now': entryAllowedNow,
    },
    'analysis': {
      'symbol': symbol,
      'market': 'KR',
      'currency': 'KRW',
      'current_price': currentPrice,
      'score': finalBuyScore,
      'final_entry_score': finalBuyScore,
      'indicator_status': 'ok',
      'indicator_payload': indicatorPayload,
      'indicator_bar_count': 100,
      'final_buy_score': finalBuyScore,
      'final_sell_score': finalSellScore,
      'confidence': 0.77,
      'risk_flags': riskFlags,
      'gating_notes': const [
        'KIS OHLCV indicators were used for quant scoring.',
      ],
      'reason':
          'EMA20<=EMA50 down/range; price below EMA20/EMA50/VWAP; RSI context',
    },
    'readiness': {
      'block_reason':
          finalBuyScore < 65 ? 'score_threshold_not_met' : noOrderReason,
      'effective_min_entry_score': 65.0,
    },
    'validation': {
      'estimated_amount': estimatedAmount,
      'available_cash': availableCash,
      'block_reasons': validationBlockReasons,
      'warnings': validationWarnings,
    },
    'market_session': {
      'is_entry_allowed_now': entryAllowedNow,
      'is_near_close': nearClose,
    },
  };
}

String _mojibakeFallbackReason() {
  return String.fromCharCodes([
    0x00EC,
    0x00A0,
    0x0095,
    0x00EB,
    0x009F,
    0x0089,
    0x0020,
    0x00EC,
    0x00A7,
    0x0080,
    0x00ED,
    0x0091,
    0x009C,
  ]);
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
    companyName: 'Samsung Electronics',
    estimatedPrice: 72000,
    estimatedNotional: 72000,
    runtimeDryRun: false,
    killSwitch: false,
    kisEnabled: true,
    kisRealOrderEnabled: true,
    marketOpen: true,
    entryAllowedNow: true,
    noNewEntryAfter: '15:00',
    currentOperationMode: 'manual_live_trading',
    maxOrderNotionalPct: 0.03,
    dailyLiveOrderRemaining: 3,
    warningLevel: 'safe',
    riskFlags: [],
    gatingNotes: [],
    submitAllowed: true,
    confirmLiveRequired: true,
    manualOnly: true,
  );
}
