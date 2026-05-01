import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/order_ticket_section.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/candidate.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/watchlist_run_result.dart';

const _samsungName = '\uC0BC\uC131\uC804\uC790';
const _krLabel = '005930 - $_samsungName - KOSPI';

void main() {
  testWidgets('KR order ticket is dry-run only and validates preview',
      (tester) async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    expect(
        find.text(
            'US order ticket not available here. Use existing manual trading run.'),
        findsOneWidget);

    controller.selectOrderMarket(PortfolioMarket.kr);
    await tester.pumpAndSettle();

    expect(find.text('DRY-RUN ONLY'), findsOneWidget);
    expect(find.text('TRADING DISABLED'), findsOneWidget);
    expect(find.text('Submit Real KIS Order'), findsOneWidget);
    expect(find.text('Real KIS trading is disabled'), findsOneWidget);
    expect(find.text('Use dry-run validation first'), findsOneWidget);

    await tester.tap(find.text('Validate Buy'));
    await tester.pumpAndSettle();

    expect(api.validationCalls, 1);
    expect(find.text('NO REAL ORDER SUBMITTED'), findsOneWidget);
    expect(find.text('DRY-RUN VALIDATED'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('watchlist defaults to US and KR preview run is enabled',
      (tester) async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    expect(find.text('US Watchlist / Alpaca'), findsOneWidget);
    expect(find.text('AAPL'), findsOneWidget);
    expect(find.text('Run US Watchlist Once'), findsOneWidget);

    controller.selectWatchlistMarket(PortfolioMarket.kr);
    await tester.pumpAndSettle();

    expect(find.text('KR Watchlist / KIS'), findsOneWidget);
    expect(find.text(_krLabel), findsOneWidget);
    expect(find.text('READ-ONLY'), findsOneWidget);
    expect(find.text('Run KR Preview'), findsOneWidget);
    expect(find.text('Run US Watchlist Once'), findsNothing);

    await tester.tap(find.text('Run KR Preview'));
    await tester.pumpAndSettle();

    expect(api.previewCalls, 1);
    expect(find.text('Quant-first \u00B7 GPT advisory only'), findsOneWidget);
    expect(find.text('NO REAL ORDER SUBMITTED'), findsOneWidget);
    expect(find.text('GPT ADVISORY'), findsOneWidget);
    expect(find.text('PRICE ONLY'), findsOneWidget);
    expect(find.text('Not calculated'), findsWidgets);
    expect(
        find.text(
            'Technical score not calculated. Reason: insufficient indicator data.'),
        findsOneWidget);
    expect(find.text('KIS OHLCV indicators not available yet'), findsOneWidget);
    expect(find.text('GPT ADVISORY CONTEXT'), findsOneWidget);
    expect(find.text('QUANT BUY'), findsNothing);
    expect(find.text('FINAL BUY'), findsNothing);
    expect(
        find.text(
            'Only current price is available; technical indicator score was not calculated.'),
        findsOneWidget);
    expect(
        find.textContaining('submit real', findRichText: true), findsNothing);

    controller.dispose();
  });
}

Widget _wrap(DashboardController controller, Widget Function() buildChild) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => buildChild(),
        ),
      ),
    ),
  );
}

class _FakeApiClient extends ApiClient {
  int validationCalls = 0;
  int previewCalls = 0;

  @override
  Future<OrderValidationResult> validateKisOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
  }) async {
    validationCalls += 1;
    return OrderValidationResult(
      provider: 'kis',
      market: 'KR',
      environment: 'prod',
      dryRun: true,
      validatedForSubmission: true,
      canSubmitLater: true,
      symbol: symbol,
      side: side,
      qty: qty,
      orderType: 'market',
      currentPrice: 72000,
      estimatedAmount: 72000,
      availableCash: 1000000,
      heldQty: null,
      warnings: const [],
      blockReasons: const [],
      marketSession: const MarketSessionStatus(
        market: 'KR',
        timezone: 'Asia/Seoul',
        isMarketOpen: true,
        isEntryAllowedNow: true,
        isNearClose: false,
      ),
      orderPreview: const OrderPreview(
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

  @override
  Future<WatchlistRunResult> runKisWatchlistPreview() async {
    previewCalls += 1;
    return const WatchlistRunResult(
      configuredSymbolCount: 1,
      analyzedSymbolCount: 1,
      quantCandidatesCount: 0,
      researchedCandidatesCount: 0,
      finalBestCandidate: '',
      secondFinalCandidate: '',
      tiedFinalCandidates: [],
      nearTiedCandidates: [],
      tieBreakerApplied: false,
      finalCandidateSelectionReason: 'KR preview only; trading disabled.',
      bestScore: null,
      finalScoreGap: null,
      minEntryScore: null,
      minScoreGap: null,
      shouldTrade: false,
      triggeredSymbol: null,
      triggerBlockReason: 'kr_trading_disabled',
      finalEntryReady: false,
      finalActionHint: 'watch',
      action: 'hold',
      orderId: null,
      topQuantCandidates: [],
      researchedCandidates: [],
      finalRankedCandidates: [
        Candidate(
          symbol: '005930',
          name: _samsungName,
          market: 'KOSPI',
          currentPrice: 72000,
          currency: 'KRW',
          score: null,
          note: 'Price-only preview; technical indicators not calculated yet.',
          indicatorStatus: 'price_only',
          indicatorPayload: {
            'ema20': null,
            'ema50': null,
            'rsi': null,
          },
          quantBuyScore: null,
          quantSellScore: null,
          aiBuyScore: null,
          aiSellScore: null,
          finalBuyScore: null,
          finalSellScore: null,
          confidence: null,
          action: 'hold',
          actionHint: 'watch',
          entryReady: false,
          tradeAllowed: false,
          approvedByRisk: false,
          blockReason: 'insufficient_indicator_data',
          reason:
              'Only current price is available; technical indicator score was not calculated.',
          gptReason: 'Advisory context only. No executable trade decision.',
          riskFlags: ['kr_trading_disabled', 'preview_only'],
          gatingNotes: [
            'KR preview uses the shared signal/risk vocabulary but trading is disabled.'
          ],
          blockReasons: ['preview_only', 'kr_trading_disabled'],
          warnings: ['preview_only', 'kr_trading_disabled'],
        ),
      ],
      result: 'preview_only',
      reason: 'kr_trading_disabled',
      triggerSource: 'manual_preview',
    );
  }
}

const _usWatchlist = MarketWatchlist(
  market: 'US',
  currency: 'USD',
  timezone: 'America/New_York',
  watchlistFile: 'config/watchlist_us.yaml',
  count: 2,
  symbols: [
    WatchlistSymbol(symbol: 'AAPL', name: '', market: 'US'),
    WatchlistSymbol(symbol: 'MSFT', name: '', market: 'US'),
  ],
);

const _krWatchlist = MarketWatchlist(
  market: 'KR',
  currency: 'KRW',
  timezone: 'Asia/Seoul',
  watchlistFile: 'config/watchlist_kr.yaml',
  count: 1,
  symbols: [
    WatchlistSymbol(symbol: '005930', name: _samsungName, market: 'KOSPI'),
  ],
);
