import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/order_ticket_section.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/candidate.dart';
import 'package:auto_invest_dashboard/models/kis_auto_simulator_result.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';
import 'package:auto_invest_dashboard/models/watchlist_run_result.dart';

const _samsungName = '\uC0BC\uC131\uC804\uC790';

void main() {
  testWidgets('KR order ticket is dry-run only and validates preview',
      (tester) async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..kisSafetyStatus = api.safetyStatus;

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    expect(find.text('REAL KIS LIVE'), findsOneWidget);
    expect(find.text('MANUAL ONLY'), findsOneWidget);
    expect(find.text('NO AUTO KIS ORDERS'), findsOneWidget);
    expect(find.text('Submit Live KIS Order'), findsOneWidget);
    expect(find.text('Use dry-run validation first'), findsOneWidget);
    expect(find.text('RUNTIME SAFETY STATUS'), findsOneWidget);
    expect(find.text('PRE-SUBMIT CHECKLIST'), findsOneWidget);
    expect(find.text('DRY_RUN'), findsOneWidget);
    expect(find.text('KILL_SWITCH'), findsOneWidget);
    expect(find.text('KIS_ENABLED'), findsOneWidget);
    expect(find.text('KIS_REAL_ORDER_ENABLED'), findsOneWidget);
    expect(find.text('MARKET_OPEN'), findsOneWidget);
    expect(find.text('ENTRY_ALLOWED_NOW'), findsOneWidget);
    expect(find.text('NO_NEW_ENTRY_AFTER'), findsOneWidget);
    expect(
      find.text('Live submit available after validation + confirmation'),
      findsOneWidget,
    );

    expect(find.textContaining('recent validation passed'), findsOneWidget);
    expect(
      find.textContaining('validation matches current symbol / qty / side'),
      findsOneWidget,
    );
    expect(find.textContaining('runtime dry_run is OFF'), findsOneWidget);
    expect(find.textContaining('KIS enabled'), findsOneWidget);
    expect(find.textContaining('KIS real order enabled'), findsOneWidget);

    await tester.tap(find.text('Validate Buy'));
    await tester.pumpAndSettle();

    expect(api.validationCalls, 1);
    expect(find.text('NO REAL ORDER SUBMITTED'), findsOneWidget);
    expect(find.text('DRY-RUN VALIDATED'), findsOneWidget);

    expect(find.textContaining('recent validation passed'), findsOneWidget);
    expect(
      find.textContaining('validation matches current symbol / qty / side'),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('KIS manual qty can be cleared without restoring default',
      (tester) async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..kisSafetyStatus = api.safetyStatus;

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    final qtyField = _qtyField();
    expect(_fieldText(tester, qtyField), '1');

    await tester.enterText(qtyField, '');
    await tester.pumpAndSettle();

    expect(_fieldText(tester, qtyField), '');
    expect(controller.orderTicketQtyInput, '');
    expect(controller.orderTicketQty, 1);
    expect(find.text('Enter quantity 1 or higher.'), findsOneWidget);
    expect(_filledButtonEnabled(tester, 'Validate Buy'), isFalse);
    expect(_filledButtonEnabled(tester, 'Submit Live KIS Order'), isFalse);

    controller.setOrderTicketSide('sell');
    await tester.pumpAndSettle();

    expect(_filledButtonEnabled(tester, 'Validate Sell'), isFalse);

    controller.dispose();
  });

  testWidgets('KIS manual qty zero disables validation and live submit',
      (tester) async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..kisSafetyStatus = api.safetyStatus;

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    final qtyField = _qtyField();
    await tester.enterText(qtyField, '0');
    await tester.pumpAndSettle();

    expect(_fieldText(tester, qtyField), '0');
    expect(controller.parsedOrderTicketQty, isNull);
    expect(find.text('Enter quantity 1 or higher.'), findsOneWidget);
    expect(_filledButtonEnabled(tester, 'Validate Buy'), isFalse);
    expect(_filledButtonEnabled(tester, 'Submit Live KIS Order'), isFalse);

    controller.dispose();
  });

  testWidgets('KIS manual qty accepts normal replacement and validates qty 2',
      (tester) async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..kisSafetyStatus = api.safetyStatus;

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    final qtyField = _qtyField();
    await tester.enterText(qtyField, '');
    await tester.pumpAndSettle();
    await tester.enterText(qtyField, '2');
    await tester.pumpAndSettle();

    expect(_fieldText(tester, qtyField), '2');
    expect(controller.parsedOrderTicketQty, 2);
    expect(controller.orderTicketQty, 2);
    expect(_filledButtonEnabled(tester, 'Validate Buy'), isTrue);

    await tester.tap(find.text('Validate Buy'));
    await tester.pumpAndSettle();

    expect(api.validationCalls, 1);
    expect(api.lastValidationQty, 2);

    controller.dispose();
  });

  testWidgets('KIS manual qty accepts 10 and keeps Ctrl+A replacement working',
      (tester) async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..kisSafetyStatus = api.safetyStatus;

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    final qtyField = _qtyField();
    await tester.enterText(qtyField, '10');
    await tester.pumpAndSettle();

    expect(_fieldText(tester, qtyField), '10');
    expect(controller.parsedOrderTicketQty, 10);

    await tester.tap(qtyField);
    await tester.pump();
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyA);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.enterText(qtyField, '2');
    await tester.pumpAndSettle();

    expect(_fieldText(tester, qtyField), '2');
    expect(controller.parsedOrderTicketQty, 2);

    controller.dispose();
  });

  testWidgets('KIS manual order card shows runtime safety blocks',
      (tester) async {
    final api = _FakeApiClient(
      safetyStatus: const KisManualOrderSafetyStatus(
        runtimeDryRun: true,
        killSwitch: true,
        kisEnabled: true,
        kisRealOrderEnabled: false,
        marketOpen: true,
        entryAllowedNow: true,
        noNewEntryAfter: '15:00',
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..kisSafetyStatus = api.safetyStatus;

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    expect(find.text('DRY_RUN'), findsOneWidget);
    expect(find.text('KILL_SWITCH'), findsOneWidget);
    expect(find.text('KIS_REAL_ORDER_ENABLED'), findsOneWidget);
    expect(find.text('Live submit blocked: dry-run is ON'), findsOneWidget);
    expect(
      find.text('Live submit available after validation + confirmation'),
      findsNothing,
    );

    controller.dispose();
  });

  testWidgets('KIS manual order card shows first non-dry-run block',
      (tester) async {
    final api = _FakeApiClient(
      safetyStatus: const KisManualOrderSafetyStatus(
        runtimeDryRun: false,
        killSwitch: true,
        kisEnabled: true,
        kisRealOrderEnabled: false,
        marketOpen: true,
        entryAllowedNow: true,
        noNewEntryAfter: '15:00',
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..kisSafetyStatus = api.safetyStatus;

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    expect(
      find.text('Live submit blocked: kill switch is ON'),
      findsOneWidget,
    );
    expect(
      find.text('Live submit available after validation + confirmation'),
      findsNothing,
    );

    controller.dispose();
  });

  testWidgets('watchlist stays focused on scan and refresh actions',
      (tester) async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    expect(find.text('US new-buy scan / Alpaca'), findsOneWidget);
    expect(find.text('Watchlist Symbols'), findsOneWidget);
    expect(find.text('Start Scan'), findsOneWidget);
    expect(find.text('Refresh'), findsOneWidget);
    expect(find.text('Run Single Symbol'), findsNothing);
    expect(find.text('Validate'), findsNothing);
    expect(find.text('Submit'), findsNothing);
    expect(find.text('Live Submit'), findsNothing);
    expect(find.text('Scheduler Enable'), findsNothing);

    controller.setProvider(SelectedProvider.kis);
    await tester.pumpAndSettle();

    expect(find.text('KR new-buy scan / KIS'), findsOneWidget);
    expect(find.text('Watchlist Symbols'), findsOneWidget);
    expect(find.text('PREVIEW ONLY'), findsOneWidget);
    expect(find.text('TRADING DISABLED'), findsOneWidget);
    expect(find.text('NO AUTO ORDER'), findsOneWidget);
    expect(find.text('Start Scan'), findsOneWidget);
    expect(find.text('Refresh'), findsOneWidget);
    expect(find.text('Run KIS Preview'), findsNothing);
    expect(find.text('Run Single Symbol'), findsNothing);

    await tester.tap(find.text('Start Scan'));
    await tester.pumpAndSettle();

    expect(api.previewCalls, 1);
    expect(api.lastProvider, 'kis');
    expect(api.lastGateLevel, 2);
    expect(api.lastKisGateLevel, 2);
    expect(controller.runResult.result, 'preview_only');
    expect(controller.runResult.finalRankedCandidates.single.indicatorStatus,
        'price_only');
    expect(
        find.textContaining('submit real', findRichText: true), findsNothing);
    expect(api.validationCalls, 0);

    controller.dispose();
  });

  testWidgets('KR scan displays a readable top candidate summary',
      (tester) async {
    final api = _FakeApiClient(scoredPreview: true);
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    controller.setProvider(SelectedProvider.kis);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Start Scan'));
    await tester.pumpAndSettle();

    expect(find.text('PREVIEW ONLY'), findsWidgets);
    expect(find.text('TRADING DISABLED'), findsWidgets);
    expect(api.previewCalls, 1);

    final candidate = controller.runResult.finalRankedCandidates.single;
    expect(controller.runResult.result, 'preview_only');
    expect(controller.runResult.bestScore, 64);
    expect(candidate.indicatorStatus, 'ok');
    expect(candidate.quantBuyScore, 62);
    expect(candidate.quantSellScore, 18);
    expect(candidate.aiBuyScore, 70);
    expect(candidate.finalBuyScore, 64);
    expect(candidate.confidence, 0.72);
    expect(find.text('Prepare Buy Ticket'), findsOneWidget);
    expect(find.text('Not ready'), findsWidgets);
    expect(find.text('0.72'), findsWidgets);
    expect(find.text('KIS GPT Advisory Context'), findsNothing);
    expect(find.text('AI_BUY_SCORE'), findsNothing);
    expect(find.textContaining('GPT approved'), findsNothing);
    expect(
        candidate.indicatorPayload.keys,
        containsAll(<String>[
          'ema20',
          'ema50',
          'rsi',
          'vwap',
          'atr',
          'volume_ratio',
          'momentum',
          'recent_return',
        ]));

    controller.dispose();
  });

  testWidgets('Prepare Buy Ticket only prefills Manual Order state',
      (tester) async {
    final api = _FakeApiClient(scoredPreview: true);
    var openedManualOrder = false;
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(
        controller: controller,
        onOpenManualOrder: () => openedManualOrder = true,
      ),
    ));

    controller.setProvider(SelectedProvider.kis);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Start Scan'));
    await tester.pumpAndSettle();
    await tester.dragUntilVisible(
      find.text('Prepare Buy Ticket'),
      find.byType(ListView),
      const Offset(0, -200),
    );
    await tester.tap(find.text('Prepare Buy Ticket'));
    await tester.pumpAndSettle();

    expect(openedManualOrder, isTrue);
    expect(controller.selectedOrderMarket, PortfolioMarket.kr);
    expect(controller.orderTicketSymbol, '005930');
    expect(controller.orderTicketSide, 'buy');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(
        controller.orderTicketSourceMetadata?['source'], 'watchlist_candidate');
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);

    controller.dispose();
  });

  testWidgets('Watchlist Start Scan shows Alpaca summary and no order created',
      (tester) async {
    final api =
        _FakeApiClient(runWatchlistDelay: const Duration(milliseconds: 50));
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    await tester.tap(find.text('Start Scan'));
    await tester.pump(const Duration(milliseconds: 10));

    expect(find.text('Scanning...'), findsOneWidget);
    await tester.pumpAndSettle();

    expect(api.lastProvider, 'alpaca');
    expect(find.text('WMT'), findsWidgets);
    expect(find.text('No order created'), findsWidgets);
    expect(find.text('SKIPPED'), findsOneWidget);
    expect(find.text('PRIMARY SCORE'), findsWidgets);
    expect(find.text('CONFIDENCE'), findsWidgets);
    expect(find.text('READINESS'), findsWidgets);
    expect(find.text('Not ready'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Watchlist Start Scan renders realistic result summary in place',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 1800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeApiClient(
      watchlistPayload: _realisticWatchlistPayload(
        symbol: 'LRCX',
        entryScore: 72,
        quantBuyScore: 72,
        aiBuyScore: 72,
        aiSellScore: 21,
        blockReason: 'hard_blocked',
        entryPenalty: 999,
        hardBlockNewBuy: true,
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    await tester.tap(find.text('Start Scan'));
    await tester.pumpAndSettle();

    expect(api.lastProvider, 'alpaca');
    expect(find.text('Latest Scan Summary'), findsOneWidget);
    expect(find.text('LRCX'), findsWidgets);
    expect(find.text('RESULT'), findsWidgets);
    expect(find.text('Blocked'), findsWidgets);
    expect(find.text('PRIMARY SCORE'), findsWidgets);
    expect(find.text('72'), findsWidgets);
    expect(find.text('CONFIDENCE'), findsWidgets);
    expect(find.text('0.81'), findsOneWidget);
    expect(find.text('QUANT BUY'), findsOneWidget);
    expect(find.text('AI BUY'), findsWidgets);
    expect(find.text('AI SELL'), findsWidgets);
    expect(find.text('21'), findsWidgets);
    expect(find.text('No order created'), findsWidgets);
    expect(find.textContaining('hard_blocked'), findsNothing);
    expect(find.text('Entry blocked by GPT/risk context'), findsWidgets);
    expect(find.text('999'), findsNothing);
    expect(find.text('Analysis Details'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Watchlist skipped result renders no-order and block reason',
      (tester) async {
    final api = _FakeApiClient(
      watchlistPayload: _realisticWatchlistPayload(
        result: 'skipped',
        blockReason: 'risk_gate_blocked',
        aiBuyScore: 63,
        aiSellScore: 19,
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    await tester.tap(find.text('Start Scan'));
    await tester.pumpAndSettle();

    expect(find.text('Skipped'), findsWidgets);
    expect(find.text('No order created'), findsWidgets);
    expect(find.text('Safety gate blocked'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Watchlist candidate list preview shows top candidates',
      (tester) async {
    final api = _FakeApiClient(
      watchlistPayload: _multiCandidateWatchlistPayload(),
    );
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    await tester.tap(find.text('Start Scan'));
    await tester.pumpAndSettle();

    expect(find.text('Top Watchlist Candidates'), findsOneWidget);
    expect(find.text('NVDA'), findsWidgets);
    expect(find.textContaining('AAPL'), findsWidgets);
    expect(find.textContaining('MSFT'), findsWidgets);
    expect(find.text('Score below entry threshold'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Watchlist candidate expands company and technical details',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeApiClient(
      watchlistPayload: _realisticWatchlistPayload(
        symbol: '005930',
        name: 'Samsung Electronics',
        blockReason: 'buy_sell_spread_too_weak',
        entryScore: 58,
        quantBuyScore: 58,
        quantSellScore: 18,
        aiBuyScore: 60,
        aiSellScore: 20,
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    await tester.tap(find.text('Start Scan'));
    await tester.pumpAndSettle();

    expect(find.text('005930 · Samsung Electronics'), findsWidgets);
    expect(find.textContaining('Watch · Buy 58 / Required 65 · Sell 18'),
        findsOneWidget);
    expect(find.text('Blocked: Buy-sell spread too weak'), findsWidgets);

    await tester.tap(find.text('005930 · Samsung Electronics').last);
    await tester.pumpAndSettle();

    expect(find.text('Candidate Identity'), findsOneWidget);
    expect(find.text('COMPANY'), findsOneWidget);
    expect(find.text('Samsung Electronics'), findsWidgets);
    expect(find.text('MARKET / PROVIDER'), findsOneWidget);
    expect(find.text('KIS / KOSPI'), findsWidgets);
    expect(find.text('Score Detail'), findsOneWidget);
    expect(find.text('REQUIRED THRESHOLD'), findsOneWidget);
    expect(find.text('Technical Snapshot'), findsOneWidget);
    expect(find.text('EMA20'), findsOneWidget);
    expect(find.text('VWAP'), findsOneWidget);
    expect(find.text('RSI'), findsOneWidget);
    expect(find.text('Advisory / Risk'), findsOneWidget);
    expect(find.textContaining('Why not tradable: Buy-sell spread too weak'),
        findsOneWidget);

    controller.dispose();
  });

  testWidgets('Watchlist candidate with symbol only shows company fallback',
      (tester) async {
    final api = _FakeApiClient(
      watchlistPayload: _realisticWatchlistPayload(symbol: 'AAPL'),
    );
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    await tester.tap(find.text('Start Scan'));
    await tester.pumpAndSettle();

    expect(find.text('AAPL · Unknown company'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Watchlist no-candidate result still shows skipped summary',
      (tester) async {
    final api = _FakeApiClient(
      watchlistPayload: _noCandidateWatchlistPayload(),
    );
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    await tester.tap(find.text('Start Scan'));
    await tester.pumpAndSettle();

    expect(find.text('No top candidate'), findsOneWidget);
    expect(find.text('No order created'), findsWidgets);
    expect(find.text('Safety gate blocked'), findsWidgets);
    expect(
        find.text('No top candidate yet. Start a scan to rank the watchlist.'),
        findsOneWidget);

    controller.dispose();
  });

  testWidgets('Watchlist GPT score fallback is explicit when absent',
      (tester) async {
    final api = _FakeApiClient(
      watchlistPayload: _realisticWatchlistPayload(
        aiBuyScore: null,
        aiSellScore: null,
        buyScore: null,
        sellScore: null,
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    await tester.tap(find.text('Start Scan'));
    await tester.pumpAndSettle();

    expect(find.text('AI BUY'), findsWidgets);
    expect(find.text('AI SELL'), findsWidgets);
    expect(find.text('GPT BUY'), findsOneWidget);
    expect(find.text('GPT SELL'), findsOneWidget);
    expect(find.text('No numeric GPT score returned'), findsNWidgets(2));

    controller.dispose();
  });

  test('WatchlistRunResult parses final_best_candidate map and list fallback',
      () {
    final fromMap = WatchlistRunResult.fromJson(
      _realisticWatchlistPayload(aiBuyScore: 68, aiSellScore: 21),
    );

    expect(fromMap.finalBestCandidate, 'AAPL');
    expect(fromMap.finalRankedCandidates.single.entryScore, 74);
    expect(fromMap.finalRankedCandidates.single.quantScore, 70);
    expect(fromMap.finalRankedCandidates.single.aiBuyScore, 68);
    expect(fromMap.finalRankedCandidates.single.softEntryAllowed, isFalse);
    expect(fromMap.finalRankedCandidates.single.noOrderReason,
        'risk gate blocked order creation');

    final fromList = WatchlistRunResult.fromJson({
      ..._realisticWatchlistPayload(aiBuyScore: 64, aiSellScore: 18),
      'final_ranked_candidates': null,
      'final_best_candidate': [
        _realisticCandidatePayload(aiBuyScore: 64, aiSellScore: 18),
      ],
    });

    expect(fromList.finalBestCandidate, 'AAPL');
    expect(fromList.finalRankedCandidates, hasLength(1));
    expect(fromList.finalRankedCandidates.single.finalEntryScore, 74);
    expect(fromList.finalRankedCandidates.single.aiSellScore, 18);
  });

  test('WatchlistRunResult parses KIS preview candidate fields', () {
    final result = WatchlistRunResult.fromJson(_kisPreviewPayload());

    expect(result.finalBestCandidate, '005930');
    expect(result.result, 'preview_only');
    expect(result.finalRankedCandidates, hasLength(1));
    final candidate = result.finalRankedCandidates.single;
    expect(candidate.symbol, '005930');
    expect(candidate.finalEntryScore, 52);
    expect(candidate.finalBuyScore, 52);
    expect(candidate.aiBuyScore, 37);
    expect(candidate.confidence, 0.69);
    expect(candidate.blockReason, 'kr_trading_disabled');
    expect(candidate.gptReason, 'KR preview advisory reason');
    expect(candidate.previewOnly, isTrue);
    expect(candidate.tradingEnabled, isFalse);
    expect(candidate.realOrderSubmitted, isFalse);
  });

  testWidgets('Watchlist Refresh reloads watchlist and latest run summary',
      (tester) async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => WatchlistSection(controller: controller),
    ));

    await tester.tap(find.text('Refresh'));
    await tester.pumpAndSettle();

    expect(api.refreshLatestCalls, 1);
    expect(find.text('WMT'), findsWidgets);
    expect(find.text('Watchlist refreshed.'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Test Lab exposes advanced checks outside Watchlist',
      (tester) async {
    final controller = DashboardController(_FakeApiClient(), autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => TestLabSection(controller: controller),
    ));

    expect(find.text('Run Buy Shadow'), findsOneWidget);
    expect(find.text('Run Exit Shadow'), findsOneWidget);
    expect(find.text('Run Scheduler Dry-run'), findsOneWidget);
    expect(find.text('Run KIS Preview'), findsOneWidget);
    expect(find.text('Run Limited Auto Buy Check'), findsOneWidget);
    expect(find.text('Run Stop-Loss Preflight'), findsWidgets);
    expect(find.text('Run Scheduler Live Guarded Check'), findsOneWidget);
    expect(find.text('Refresh Readiness'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('Live Submit'), findsNothing);

    controller.dispose();
  });

  testWidgets('KIS Auto Simulator runs dry-run auto and shows last result',
      (tester) async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..usWatchlist = _usWatchlist
      ..krWatchlist = _krWatchlist;

    await tester.pumpWidget(_wrap(
      controller,
      () => TestLabSection(controller: controller),
    ));

    controller.setProvider(SelectedProvider.kis);
    await tester.pumpAndSettle();

    expect(find.text('KIS Auto Simulator'), findsOneWidget);
    expect(find.text('Dry-run only'), findsOneWidget);
    expect(find.text('Run KIS Dry-Run Auto'), findsOneWidget);

    await tester.ensureVisible(find.text('Run KIS Dry-Run Auto'));
    await tester.tap(find.text('Run KIS Dry-Run Auto'));
    await tester.pumpAndSettle();

    expect(api.dryRunAutoCalls, 1);
    expect(api.lastDryRunGateLevel, 2);
    expect(controller.kisAutoSimulatorResult?.realOrderSubmitted, isFalse);
    expect(find.text('real_order_submitted=false'), findsWidgets);
    expect(find.text('simulated_order_created'), findsWidgets);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('123'), findsOneWidget);
    expect(find.text('456'), findsOneWidget);
    expect(find.text('74'), findsOneWidget);
    expect(find.text('82'), findsOneWidget);
    expect(find.text('76'), findsOneWidget);
    expect(
      find.text('KIS dry-run auto completed: simulated_order_created.'),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('Sync Open KIS Orders calls API and refreshes recent orders',
      (tester) async {
    final api = _FakeApiClient(
      syncOpenCount: 2,
      orders: [_kisOrder(orderId: 1, status: 'SUBMITTED')],
      refreshedOrders: [_kisOrder(orderId: 2, status: 'ACCEPTED')],
      summary: const KisOrderSummary(
        openOrders: 1,
        filledToday: 2,
        canceledToday: 1,
        rejectedToday: 0,
        lastOrderAt: '2026-05-08T00:04:00',
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..latestKisManualOrder = _kisOrder(orderId: 1, status: 'SUBMITTED')
      ..selectedKisOrder = _kisOrder(orderId: 1, status: 'SUBMITTED')
      ..kisOrders = [_kisOrder(orderId: 1, status: 'SUBMITTED')];

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    await tester.ensureVisible(find.text('Sync Open KIS Orders'));
    await tester.tap(find.text('Sync Open KIS Orders'));
    await tester.pumpAndSettle();

    expect(api.syncOpenCalls, 1);
    expect(api.fetchKisOrdersCalls, 1);
    expect(controller.kisOrders.first.orderId, 2);
    expect(find.text('Open KIS orders synced: 2 updated.'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('KIS order actions are visible only for syncable open orders',
      (tester) async {
    final api = _FakeApiClient();
    final openOrder = _kisOrder(orderId: 1, status: 'SUBMITTED');
    final controller = DashboardController(api, autoload: false)
      ..latestKisManualOrder = openOrder
      ..selectedKisOrder = openOrder
      ..kisOrders = [openOrder];

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    expect(find.text('Sync Status'), findsWidgets);
    expect(find.text('Cancel Order'), findsOneWidget);
    expect(find.text('INTERNAL STATUS'), findsOneWidget);
    expect(find.text('BROKER STATUS'), findsOneWidget);
    expect(find.text('CREATED'), findsOneWidget);
    expect(find.text('LAST SYNC'), findsOneWidget);
    expect(find.text('STATE'), findsOneWidget);

    final terminalOrder = _kisOrder(orderId: 2, status: 'FILLED');
    controller
      ..latestKisManualOrder = terminalOrder
      ..selectedKisOrder = terminalOrder
      ..kisOrders = [terminalOrder]
      ..notifyListeners();
    await tester.pumpAndSettle();

    expect(find.text('Sync Status'), findsNothing);
    expect(find.text('Cancel Order'), findsNothing);
    expect(find.text('FILLED'), findsWidgets);

    controller.dispose();
  });

  testWidgets('KIS cancel hides for rejected and missing ODNO orders',
      (tester) async {
    final api = _FakeApiClient();
    final rejectedOrder =
        _kisOrder(orderId: 1, status: 'REJECTED_BY_SAFETY_GATE');
    final controller = DashboardController(api, autoload: false)
      ..latestKisManualOrder = rejectedOrder
      ..selectedKisOrder = rejectedOrder
      ..kisOrders = [rejectedOrder];

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    expect(find.text('Cancel Order'), findsNothing);
    expect(find.text('REJECTED'), findsWidgets);

    final noOdnoOrder =
        _kisOrder(orderId: 2, status: 'SUBMITTED', kisOdno: null);
    controller
      ..latestKisManualOrder = noOdnoOrder
      ..selectedKisOrder = noOdnoOrder
      ..kisOrders = [noOdnoOrder]
      ..notifyListeners();
    await tester.pumpAndSettle();

    expect(find.text('Sync Status'), findsWidgets);
    expect(find.text('Cancel Order'), findsNothing);

    controller.dispose();
  });

  testWidgets('KIS cancel requires confirmation and refreshes orders',
      (tester) async {
    final openOrder = _kisOrder(orderId: 1, status: 'SUBMITTED');
    final canceledOrder = _kisOrder(orderId: 1, status: 'CANCELED');
    final api = _FakeApiClient(
      orders: [openOrder],
      cancelDetail: canceledOrder,
      refreshedOrders: [canceledOrder],
    );
    final controller = DashboardController(api, autoload: false)
      ..latestKisManualOrder = openOrder
      ..selectedKisOrder = openOrder
      ..kisOrders = [openOrder];

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    await tester.ensureVisible(find.text('Cancel Order').first);
    await tester.tap(find.text('Cancel Order').first);
    await tester.pumpAndSettle();

    expect(api.cancelCalls, 0);
    expect(
      find.text(
        'Cancel this KIS order? This only cancels the existing open order and will not create a new order.',
      ),
      findsOneWidget,
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Cancel Order'));
    await tester.pumpAndSettle();

    expect(api.cancelCalls, 1);
    expect(api.fetchKisOrderDetailCalls, 1);
    expect(api.fetchKisOrdersCalls, 1);
    expect(controller.selectedKisOrder?.clearStatusLabel, 'CANCELED');
    expect(find.text('KIS order canceled.'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('KIS cancel error snackbar uses concise message', (tester) async {
    final openOrder = _kisOrder(orderId: 1, status: 'SUBMITTED');
    final api = _FakeApiClient(orders: [openOrder], throwCancel: true);
    final controller = DashboardController(api, autoload: false)
      ..latestKisManualOrder = openOrder
      ..selectedKisOrder = openOrder
      ..kisOrders = [openOrder];

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    await tester.ensureVisible(find.text('Cancel Order').first);
    await tester.tap(find.text('Cancel Order').first);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Cancel Order'));
    await tester.pumpAndSettle();

    expect(api.cancelCalls, 1);
    expect(
      find.descendant(
        of: find.byType(SnackBar),
        matching: find.text('Terminal orders cannot be canceled.'),
      ),
      findsOneWidget,
    );
    expect(find.text('Order error details'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('KIS order polling stops on terminal state', (tester) async {
    final openOrder = _kisOrder(orderId: 1, status: 'SUBMITTED');
    final filledOrder = _kisOrder(orderId: 1, status: 'FILLED');
    final api = _FakeApiClient(
      orders: [openOrder],
      refreshedOrders: [filledOrder],
      syncResults: [filledOrder],
    );
    final controller = DashboardController(api, autoload: false)
      ..latestKisManualOrder = openOrder
      ..selectedKisOrder = openOrder
      ..kisOrders = [openOrder];

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    await tester.pump(const Duration(seconds: 21));
    await tester.pumpAndSettle();

    expect(api.syncOrderCalls, 1);
    expect(controller.selectedKisOrder?.clearStatusLabel, 'FILLED');

    await tester.pump(const Duration(seconds: 21));
    await tester.pump();

    expect(api.syncOrderCalls, 1);

    controller.dispose();
  });

  testWidgets('KIS order polling stops on dispose', (tester) async {
    final openOrder = _kisOrder(orderId: 1, status: 'SUBMITTED');
    final api = _FakeApiClient(
      orders: [openOrder],
      refreshedOrders: [openOrder],
      syncResults: [openOrder, openOrder],
    );
    final controller = DashboardController(api, autoload: false)
      ..latestKisManualOrder = openOrder
      ..selectedKisOrder = openOrder
      ..kisOrders = [openOrder];

    await tester.pumpWidget(_wrap(
      controller,
      () => OrderTicketSection(controller: controller),
    ));

    await tester.pump(const Duration(seconds: 21));
    await tester.pump();
    expect(api.syncOrderCalls, 1);

    await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
    await tester.pump(const Duration(seconds: 21));
    await tester.pump();

    expect(api.syncOrderCalls, 1);

    controller.dispose();
  });

  test('KIS order filter and sort behavior', () {
    final controller = DashboardController(_FakeApiClient(), autoload: false)
      ..kisOrders = [
        _kisOrder(
          orderId: 1,
          status: 'SUBMITTED',
          createdAt: '2026-05-08T00:01:00',
        ),
        _kisOrder(
          orderId: 2,
          status: 'FILLED',
          createdAt: '2026-05-08T00:02:00',
        ),
        _kisOrder(
          orderId: 3,
          status: 'CANCELED',
          createdAt: '2026-05-08T00:03:00',
        ),
        _kisOrder(
          orderId: 4,
          status: 'REJECTED_BY_SAFETY_GATE',
          createdAt: '2026-05-08T00:04:00',
        ),
      ];

    expect(controller.visibleKisOrders.map((order) => order.orderId),
        [4, 3, 2, 1]);

    controller.setKisOrderFilter(KisOrderHistoryFilter.open);
    expect(controller.visibleKisOrders.map((order) => order.orderId), [1]);

    controller.setKisOrderFilter(KisOrderHistoryFilter.filled);
    expect(controller.visibleKisOrders.map((order) => order.orderId), [2]);

    controller.setKisOrderFilter(KisOrderHistoryFilter.canceled);
    expect(controller.visibleKisOrders.map((order) => order.orderId), [3]);

    controller.setKisOrderFilter(KisOrderHistoryFilter.rejected);
    expect(controller.visibleKisOrders.map((order) => order.orderId), [4]);

    controller.setKisOrderFilter(KisOrderHistoryFilter.all);
    controller.setKisOrderSort(KisOrderHistorySort.oldestFirst);
    expect(controller.visibleKisOrders.map((order) => order.orderId),
        [1, 2, 3, 4]);

    controller.dispose();
  });

  test('duplicate KIS cancel requests are ignored while in progress', () async {
    final openOrder = _kisOrder(orderId: 1, status: 'SUBMITTED');
    final canceledOrder = _kisOrder(orderId: 1, status: 'CANCELED');
    final api = _FakeApiClient(
      orders: [openOrder],
      refreshedOrders: [canceledOrder],
      cancelDetail: canceledOrder,
      cancelDelay: const Duration(milliseconds: 20),
    );
    final controller = DashboardController(api, autoload: false)
      ..selectedKisOrder = openOrder
      ..kisOrders = [openOrder];

    final first = controller.cancelKisOrderById(1);
    final second = await controller.cancelKisOrderById(1);
    final firstResult = await first;

    expect(api.cancelCalls, 1);
    expect(second.success, isFalse);
    expect(second.message, 'KIS cancel already in progress.');
    expect(firstResult.success, isTrue);

    controller.dispose();
  });

  test('duplicate KIS sync requests are ignored while in progress', () async {
    final openOrder = _kisOrder(orderId: 1, status: 'SUBMITTED');
    final api = _FakeApiClient(
      orders: [openOrder],
      refreshedOrders: [openOrder],
      syncResults: [openOrder],
      syncDelay: const Duration(milliseconds: 20),
    );
    final controller = DashboardController(api, autoload: false)
      ..selectedKisOrder = openOrder
      ..kisOrders = [openOrder];

    final first = controller.syncKisOrderById(1);
    final second = await controller.syncKisOrderById(1);
    final firstResult = await first;

    expect(api.syncOrderCalls, 1);
    expect(second.success, isFalse);
    expect(second.message, 'KIS sync already in progress.');
    expect(firstResult.success, isTrue);

    controller.dispose();
  });

  test('duplicate KIS dry-run auto requests are ignored while in progress',
      () async {
    final api = _FakeApiClient(
      dryRunAutoDelay: const Duration(milliseconds: 20),
    );
    final controller = DashboardController(api, autoload: false);

    final first = controller.runKisDryRunAuto();
    final second = await controller.runKisDryRunAuto();
    final firstResult = await first;

    expect(api.dryRunAutoCalls, 1);
    expect(second.success, isFalse);
    expect(second.message, 'KIS dry-run auto already in progress.');
    expect(firstResult.success, isTrue);
    expect(controller.kisAutoSimulatorResult?.realOrderSubmitted, isFalse);

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

Finder _qtyField() {
  return find.byWidgetPredicate(
    (widget) => widget is TextField && widget.decoration?.labelText == 'Qty',
  );
}

String _fieldText(WidgetTester tester, Finder finder) {
  return tester.widget<TextField>(finder).controller?.text ?? '';
}

bool _filledButtonEnabled(WidgetTester tester, String label) {
  final buttonFinder = find.ancestor(
    of: find.text(label),
    matching: find.byWidgetPredicate((widget) => widget is FilledButton),
  );
  final button = tester.widget<FilledButton>(
    buttonFinder.first,
  );
  return button.onPressed != null;
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient({
    this.scoredPreview = false,
    this.watchlistPayload,
    this.syncOpenCount,
    this.orders = const [],
    this.refreshedOrders,
    this.syncResults = const [],
    this.syncDelay = Duration.zero,
    this.cancelDetail,
    this.cancelDelay = Duration.zero,
    this.summary = KisOrderSummary.empty,
    this.throwCancel = false,
    this.dryRunAutoDelay = Duration.zero,
    this.runWatchlistDelay = Duration.zero,
    this.safetyStatus = const KisManualOrderSafetyStatus(
      runtimeDryRun: false,
      killSwitch: false,
      kisEnabled: true,
      kisRealOrderEnabled: true,
      marketOpen: true,
      entryAllowedNow: true,
      noNewEntryAfter: '15:00',
    ),
  });

  final bool scoredPreview;
  final Map<String, dynamic>? watchlistPayload;
  final int? syncOpenCount;
  final List<KisManualOrderResult> orders;
  final List<KisManualOrderResult>? refreshedOrders;
  final List<KisManualOrderResult> syncResults;
  final Duration syncDelay;
  final KisManualOrderResult? cancelDetail;
  final Duration cancelDelay;
  final KisOrderSummary summary;
  final bool throwCancel;
  final Duration dryRunAutoDelay;
  final Duration runWatchlistDelay;
  final KisManualOrderSafetyStatus safetyStatus;
  int validationCalls = 0;
  int submitCalls = 0;
  int? lastValidationQty;
  int? lastSubmitQty;
  int previewCalls = 0;
  int dryRunAutoCalls = 0;
  int syncOpenCalls = 0;
  int syncOrderCalls = 0;
  int fetchKisOrdersCalls = 0;
  int fetchKisOrderSummaryCalls = 0;
  int cancelCalls = 0;
  int fetchKisOrderDetailCalls = 0;
  int _syncResultIndex = 0;
  String? lastProvider;
  int? lastGateLevel;
  int? lastKisGateLevel;
  int? lastDryRunGateLevel;
  int refreshLatestCalls = 0;

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async =>
      safetyStatus;

  @override
  Future<KisOpenOrderSyncResult> syncOpenKisOrders() async {
    syncOpenCalls += 1;
    return KisOpenOrderSyncResult(
      count: syncOpenCount,
      orders: orders,
    );
  }

  @override
  Future<KisManualOrderResult> syncKisOrder(int orderId) async {
    syncOrderCalls += 1;
    if (syncDelay > Duration.zero) {
      await Future<void>.delayed(syncDelay);
    }
    if (syncResults.isNotEmpty) {
      final index = _syncResultIndex >= syncResults.length
          ? syncResults.length - 1
          : _syncResultIndex;
      _syncResultIndex += 1;
      return syncResults[index];
    }
    return (refreshedOrders ?? orders).firstWhere(
      (order) => order.orderId == orderId,
      orElse: () => _kisOrder(orderId: orderId, status: 'SUBMITTED'),
    );
  }

  @override
  Future<List<KisManualOrderResult>> fetchKisOrders({
    int limit = 20,
    bool includeRejected = false,
  }) async {
    fetchKisOrdersCalls += 1;
    return refreshedOrders ?? orders;
  }

  @override
  Future<KisOrderSummary> fetchKisOrderSummary() async {
    fetchKisOrderSummaryCalls += 1;
    return summary;
  }

  @override
  Future<KisManualOrderResult> fetchKisOrderDetail(
    int orderId, {
    bool includeSyncPayload = false,
  }) async {
    fetchKisOrderDetailCalls += 1;
    if (cancelDetail != null) return cancelDetail!;
    return (refreshedOrders ?? orders).firstWhere(
      (order) => order.orderId == orderId,
      orElse: () => _kisOrder(orderId: orderId, status: 'UNKNOWN'),
    );
  }

  @override
  Future<Map<String, dynamic>> cancelKisOrder(int orderId) async {
    cancelCalls += 1;
    if (cancelDelay > Duration.zero) {
      await Future<void>.delayed(cancelDelay);
    }
    if (throwCancel) {
      throw const ApiRequestException(
        'HTTP 409: {"canceled":false,"message":"Terminal orders cannot be canceled.","raw_payload":{"CANO":"12****78"}}',
      );
    }
    return {
      'canceled': true,
      'order_id': orderId,
      'kis_odno': '0001234567',
      'internal_status': 'CANCELED',
      'broker_status': 'CANCELED',
      'message': 'KIS order canceled.',
    };
  }

  @override
  Future<PortfolioSummary> fetchPortfolioSummary() async =>
      PortfolioSummary.empty();

  @override
  Future<PortfolioSummary> fetchUsPortfolioSummary() async =>
      PortfolioSummary.empty(currency: 'USD');

  @override
  Future<PortfolioSummary> fetchKrPortfolioSummary() async =>
      PortfolioSummary.empty(currency: 'KRW');

  @override
  Future<PortfolioSummary> fetchPortfolioSummaryForMarket(String market) {
    return market.trim().toUpperCase() == 'KR'
        ? fetchKrPortfolioSummary()
        : fetchUsPortfolioSummary();
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
    lastValidationQty = qty;
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
  Future<KisManualOrderResult> submitKisManualOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    required bool confirmLive,
    Map<String, dynamic>? sourceMetadata,
  }) async {
    submitCalls += 1;
    lastSubmitQty = qty;
    return _kisOrder(orderId: 999, status: 'SUBMITTED');
  }

  @override
  Future<WatchlistRunResult> runWatchlistForProvider({
    required String provider,
    required int gateLevel,
  }) async {
    lastProvider = provider;
    lastGateLevel = gateLevel;

    if (watchlistPayload != null) {
      return WatchlistRunResult.fromJson(watchlistPayload!);
    }

    if (provider.trim().toLowerCase() == 'kis') {
      return runKisWatchlistPreview(gateLevel: gateLevel);
    }

    return runWatchlistOnce();
  }

  @override
  Future<WatchlistRunResult?> fetchLatestWatchlistRunResult() async {
    refreshLatestCalls += 1;
    return getMockRunResult();
  }

  @override
  Future<WatchlistRunResult> runWatchlistOnce() async {
    if (runWatchlistDelay > Duration.zero) {
      await Future<void>.delayed(runWatchlistDelay);
    }
    return getMockRunResult();
  }

  @override
  Future<WatchlistRunResult> runKisWatchlistPreview({
    int gateLevel = 2,
  }) async {
    previewCalls += 1;
    lastKisGateLevel = gateLevel;
    if (scoredPreview) return _scoredPreviewResult();
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
          gptReason: 'KR preview \uCC38\uACE0\uC6A9',
          eventRiskLevel: 'low',
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

  WatchlistRunResult _scoredPreviewResult() {
    return const WatchlistRunResult(
      configuredSymbolCount: 1,
      analyzedSymbolCount: 1,
      quantCandidatesCount: 1,
      researchedCandidatesCount: 1,
      finalBestCandidate: '005930',
      secondFinalCandidate: '',
      tiedFinalCandidates: [],
      nearTiedCandidates: [],
      tieBreakerApplied: false,
      finalCandidateSelectionReason:
          'KR preview ranked by grounded KIS OHLCV scores; trading disabled.',
      bestScore: 64,
      finalScoreGap: 0,
      minEntryScore: 65,
      minScoreGap: 3,
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
          score: 64,
          note:
              'KIS OHLCV indicators available; quant score calculated for preview only.',
          indicatorStatus: 'ok',
          indicatorPayload: {
            'ema20': 70000.0,
            'ema50': 68000.0,
            'rsi': 58.5,
            'vwap': 70500.0,
            'atr': 1200.0,
            'volume_ratio': 1.2,
            'momentum': 0.018,
            'recent_return': 0.04,
          },
          quantBuyScore: 62,
          quantSellScore: 18,
          aiBuyScore: 70,
          aiSellScore: 20,
          finalBuyScore: 64,
          finalSellScore: 18.5,
          confidence: 0.72,
          action: 'hold',
          actionHint: 'watch',
          entryReady: false,
          tradeAllowed: false,
          approvedByRisk: false,
          blockReason: 'kr_trading_disabled',
          reason: 'KIS OHLCV quant indicators calculated for preview.',
          gptReason: 'KR \uC815\uB7C9 \uCC38\uACE0\uC6A9',
          eventRiskLevel: 'low',
          riskFlags: ['kr_trading_disabled', 'preview_only', 'fx_pressure'],
          gatingNotes: [
            'gpt_advisory_context_visible',
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

  @override
  Future<KisAutoSimulatorResult> runKisDryRunAuto({
    required int gateLevel,
  }) async {
    dryRunAutoCalls += 1;
    lastDryRunGateLevel = gateLevel;
    if (dryRunAutoDelay > Duration.zero) {
      await Future<void>.delayed(dryRunAutoDelay);
    }
    return const KisAutoSimulatorResult(
      provider: 'kis',
      market: 'KR',
      mode: 'kis_dry_run_auto',
      dryRun: true,
      simulated: true,
      realOrderSubmitted: false,
      brokerSubmitCalled: false,
      manualSubmitCalled: false,
      triggerSource: 'manual_kis_dry_run_auto',
      result: 'simulated_order_created',
      action: 'buy',
      triggeredSymbol: '005930',
      signalId: 123,
      orderId: 456,
      reason: 'dry_run_risk_approved',
      quantBuyScore: 74,
      quantSellScore: 12,
      aiBuyScore: 82,
      aiSellScore: 14,
      confidence: 0.74,
      finalEntryScore: 76,
      finalScoreGap: 5,
      riskFlags: ['simulated_only'],
      gatingNotes: ['Dry-run risk approved a simulated buy.'],
    );
  }

  @override
  Future<List<TradingRun>> getRecentTradingRuns() async => const [];
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

Map<String, dynamic> _realisticCandidatePayload({
  String symbol = 'AAPL',
  String? name,
  String result = 'blocked',
  String blockReason = 'market_closed',
  double entryScore = 74,
  double quantScore = 70,
  double quantBuyScore = 70,
  double quantSellScore = 16,
  double? aiBuyScore,
  double? aiSellScore,
  double? buyScore,
  double? sellScore,
  int? entryPenalty,
  bool hardBlockNewBuy = false,
}) {
  return {
    'symbol': symbol,
    if (name != null) 'company_name': name,
    'provider': RegExp(r'^\d{6}$').hasMatch(symbol) ? 'kis' : 'alpaca',
    'market': RegExp(r'^\d{6}$').hasMatch(symbol) ? 'KOSPI' : 'US',
    'currency': RegExp(r'^\d{6}$').hasMatch(symbol) ? 'KRW' : 'USD',
    'current_price': RegExp(r'^\d{6}$').hasMatch(symbol) ? 72000 : 189.45,
    'action': 'hold',
    'action_hint': 'watch',
    'entry_ready': false,
    'trade_allowed': false,
    'soft_entry_allowed': false,
    'block_reason': blockReason,
    'reason': 'Entry blocked by $blockReason',
    'entry_score': entryScore.toStringAsFixed(0),
    'final_entry_score': entryScore,
    'final_score': entryScore,
    'quant_score': quantScore,
    'final_buy_score': entryScore,
    'final_sell_score': 18,
    'effective_min_entry_score': 65,
    'buy_sell_spread': entryScore - 18,
    'buy_score': buyScore,
    'sell_score': sellScore,
    'ai_buy_score': aiBuyScore,
    'ai_sell_score': aiSellScore,
    'quant_buy_score': quantBuyScore,
    'quant_sell_score': quantSellScore,
    'confidence': '0.81',
    'indicator_status': 'ok',
    'indicator_bar_count': 100,
    'indicator_payload': {
      'ema20': RegExp(r'^\d{6}$').hasMatch(symbol) ? 70000 : 181.2,
      'ema50': RegExp(r'^\d{6}$').hasMatch(symbol) ? 68000 : 176.8,
      'vwap': RegExp(r'^\d{6}$').hasMatch(symbol) ? 70500 : 184.1,
      'rsi': 58.5,
      'atr': RegExp(r'^\d{6}$').hasMatch(symbol) ? 1200 : 3.2,
      'volume_ratio': 1.24,
      'recent_return': 0.041,
      'momentum': 0.018,
      'price_position': 'above EMA20 and VWAP',
    },
    'order_id': null,
    'result': result,
    'status': result,
    'skip_reason': blockReason,
    'no_order_reason': 'risk gate blocked order creation',
    'entry_penalty': entryPenalty,
    'hard_block_new_buy': hardBlockNewBuy,
    'gpt_context': {
      'hard_block_new_buy': hardBlockNewBuy,
      'entry_penalty': entryPenalty,
      'reason': 'GPT hard block is active for this entry.',
      'gpt_buy_score': null,
      'gpt_sell_score': null,
    },
  };
}

Map<String, dynamic> _realisticWatchlistPayload({
  String symbol = 'AAPL',
  String? name,
  String result = 'blocked',
  String blockReason = 'market_closed',
  double entryScore = 74,
  double quantScore = 70,
  double quantBuyScore = 70,
  double quantSellScore = 16,
  double? aiBuyScore,
  double? aiSellScore,
  double? buyScore,
  double? sellScore,
  int? entryPenalty,
  bool hardBlockNewBuy = false,
}) {
  final candidate = _realisticCandidatePayload(
    symbol: symbol,
    name: name,
    result: result,
    blockReason: blockReason,
    entryScore: entryScore,
    quantScore: quantScore,
    quantBuyScore: quantBuyScore,
    quantSellScore: quantSellScore,
    aiBuyScore: aiBuyScore,
    aiSellScore: aiSellScore,
    buyScore: buyScore,
    sellScore: sellScore,
    entryPenalty: entryPenalty,
    hardBlockNewBuy: hardBlockNewBuy,
  );

  return {
    'configured_symbol_count': 2,
    'analyzed_symbol_count': 2,
    'quant_candidates_count': 1,
    'researched_candidates_count': 1,
    'best_score': entryScore.toStringAsFixed(0),
    'should_trade': false,
    'final_entry_ready': false,
    'final_action_hint': 'watch',
    'result': result,
    'reason': blockReason,
    'order_id': null,
    'final_best_candidate': candidate,
    'final_ranked_candidates': [candidate],
  };
}

Map<String, dynamic> _multiCandidateWatchlistPayload() {
  final candidates = [
    _realisticCandidatePayload(
      symbol: 'NVDA',
      blockReason: 'score_threshold_not_met',
      entryScore: 64,
      quantScore: 63,
      aiBuyScore: 67,
      aiSellScore: 20,
    ),
    _realisticCandidatePayload(
      symbol: 'AAPL',
      blockReason: 'score_threshold_not_met',
      entryScore: 61,
      quantScore: 60,
      aiBuyScore: 65,
      aiSellScore: 21,
    ),
    _realisticCandidatePayload(
      symbol: 'MSFT',
      blockReason: 'score_threshold_not_met',
      entryScore: 59,
      quantScore: 58,
      aiBuyScore: 60,
      aiSellScore: 24,
    ),
  ];

  return {
    'configured_symbol_count': 50,
    'analyzed_symbol_count': 50,
    'quant_candidates_count': 3,
    'researched_candidates_count': 3,
    'best_score': 64,
    'should_trade': false,
    'result': 'skipped',
    'reason': 'score_threshold_not_met',
    'final_best_candidate': candidates.first,
    'final_ranked_candidates': candidates,
  };
}

Map<String, dynamic> _kisPreviewPayload() {
  final candidate = {
    'symbol': '005930',
    'name': _samsungName,
    'market': 'KOSPI',
    'score': 52,
    'final_entry_score': 52,
    'final_buy_score': 52,
    'final_sell_score': 18,
    'quant_score': 55,
    'quant_buy_score': 54,
    'quant_sell_score': 14,
    'ai_buy_score': 37,
    'ai_sell_score': 9,
    'confidence': 0.69,
    'gpt_reason': 'KR preview advisory reason',
    'gpt_used': true,
    'block_reason': 'kr_trading_disabled',
    'block_reasons': ['kr_trading_disabled'],
    'risk_flags': ['preview_only'],
    'gating_notes': ['trading disabled'],
    'preview_only': true,
    'trading_enabled': false,
    'real_order_submitted': false,
    'action_hint': 'watch',
    'entry_ready': false,
  };

  return {
    'configured_symbol_count': 1,
    'analyzed_symbol_count': 1,
    'quant_candidates_count': 1,
    'researched_candidates_count': 1,
    'result': 'preview_only',
    'reason': 'kr_trading_disabled',
    'final_best_candidate': candidate,
    'final_ranked_candidates': [candidate],
  };
}

Map<String, dynamic> _noCandidateWatchlistPayload() {
  return {
    'configured_symbol_count': 2,
    'analyzed_symbol_count': 2,
    'quant_candidates_count': 0,
    'researched_candidates_count': 0,
    'best_score': null,
    'should_trade': false,
    'final_entry_ready': false,
    'final_action_hint': 'watch',
    'result': 'skipped',
    'reason': 'all_candidates_blocked',
    'trigger_block_reason': 'all_candidates_blocked',
    'order_id': null,
    'final_best_candidate': null,
    'final_ranked_candidates': [],
  };
}

KisManualOrderResult _kisOrder({
  required int orderId,
  required String status,
  String? kisOdno = '0001234567',
  String createdAt = '2026-05-08T00:00:00',
}) {
  final internalStatus = status.toUpperCase();
  return KisManualOrderResult.fromJson({
    'order_id': orderId,
    'broker': 'kis',
    'market': 'KR',
    'symbol': '005930',
    'side': 'buy',
    'order_type': 'market',
    'requested_qty': 3,
    'filled_qty': internalStatus == 'FILLED' ? 3 : 0,
    'remaining_qty': internalStatus == 'FILLED' ? 0 : 3,
    'avg_fill_price': internalStatus == 'FILLED' ? 72000 : null,
    'kis_odno': kisOdno,
    'internal_status': internalStatus,
    'broker_order_status': internalStatus == 'CANCELED'
        ? 'CANCELED'
        : internalStatus == 'FILLED'
            ? 'filled'
            : 'submitted',
    'created_at': createdAt,
    'submitted_at': '2026-05-08T00:01:00',
    'filled_at': internalStatus == 'FILLED' ? '2026-05-08T00:03:00' : null,
    'canceled_at': internalStatus == 'CANCELED' ? '2026-05-08T00:03:00' : null,
    'last_synced_at': '2026-05-08T00:02:00',
    'sync_error': null,
    'is_syncable': const {
      'SUBMITTED',
      'ACCEPTED',
      'PARTIALLY_FILLED',
      'UNKNOWN_STALE',
      'SYNC_FAILED',
    }.contains(internalStatus),
    'is_terminal': const {
      'FILLED',
      'REJECTED',
      'REJECTED_BY_SAFETY_GATE',
      'CANCELED',
      'FAILED',
    }.contains(internalStatus),
  });
}
