import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/order_ticket_section.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/candidate.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';
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

    expect(find.text('REAL KIS LIVE'), findsOneWidget);
    expect(find.text('MANUAL ONLY'), findsOneWidget);
    expect(find.text('NO AUTO KIS ORDERS'), findsOneWidget);
    expect(find.text('Submit Live KIS Order'), findsOneWidget);
    expect(find.text('Use dry-run validation first'), findsOneWidget);
    expect(find.text('RUNTIME SAFETY STATUS'), findsOneWidget);
    expect(find.text('PRE-SUBMIT CHECKLIST'), findsOneWidget);

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
    expect(find.text('Run Alpaca Watchlist'), findsOneWidget);

    controller.setProvider(SelectedProvider.kis);
    await tester.pumpAndSettle();

    expect(find.text('KR Watchlist / KIS'), findsOneWidget);
    expect(find.text(_krLabel), findsOneWidget);
    expect(find.text('PREVIEW ONLY'), findsOneWidget);
    expect(find.text('TRADING DISABLED'), findsOneWidget);
    expect(find.text('NO AUTO ORDER'), findsOneWidget);
    expect(find.text('Run KIS Preview'), findsOneWidget);
    expect(find.text('Run Alpaca Watchlist'), findsNothing);

    await tester.tap(find.text('Run KIS Preview'));
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

  testWidgets('KR preview displays grounded scores and indicators',
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

    await tester.tap(find.text('Run KIS Preview'));
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
  _FakeApiClient({
    this.scoredPreview = false,
    this.syncOpenCount,
    this.orders = const [],
    this.refreshedOrders,
    this.syncResults = const [],
    this.syncDelay = Duration.zero,
    this.cancelDetail,
    this.cancelDelay = Duration.zero,
    this.summary = KisOrderSummary.empty,
    this.throwCancel = false,
  });

  final bool scoredPreview;
  final int? syncOpenCount;
  final List<KisManualOrderResult> orders;
  final List<KisManualOrderResult>? refreshedOrders;
  final List<KisManualOrderResult> syncResults;
  final Duration syncDelay;
  final KisManualOrderResult? cancelDetail;
  final Duration cancelDelay;
  final KisOrderSummary summary;
  final bool throwCancel;
  int validationCalls = 0;
  int previewCalls = 0;
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

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async =>
      const KisManualOrderSafetyStatus(
        runtimeDryRun: false,
        killSwitch: false,
        kisEnabled: true,
        kisRealOrderEnabled: true,
        marketOpen: true,
        entryAllowedNow: true,
        noNewEntryAfter: '15:00',
      );

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
  Future<WatchlistRunResult> runWatchlistForProvider({
    required String provider,
    required int gateLevel,
  }) async {
    lastProvider = provider;
    lastGateLevel = gateLevel;

    if (provider.trim().toLowerCase() == 'kis') {
      return runKisWatchlistPreview(gateLevel: gateLevel);
    }

    return runWatchlistOnce();
  }

  @override
  Future<WatchlistRunResult> runWatchlistOnce() async => getMockRunResult();

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
