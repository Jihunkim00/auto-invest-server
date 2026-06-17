import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/portfolio_snapshot_section.dart';
import 'package:auto_invest_dashboard/models/automation_runtime_monitor.dart';
import 'package:auto_invest_dashboard/models/managed_position.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';

void main() {
  testWidgets('Portfolio Snapshot switches between USD and KRW summaries',
      (tester) async {
    final controller = await _pumpSnapshot(tester);

    expect(find.text('US Portfolio / Alpaca Paper'), findsOneWidget);
    expect(find.text(r'$1,000.00'), findsOneWidget);
    expect(find.text('CASH'), findsOneWidget);
    expect(find.text(r'$123.45'), findsOneWidget);
    expect(find.text('₩1,200,000'), findsNothing);
    expect(find.text('+25.00%'), findsOneWidget);

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    expect(find.text('KR Portfolio / KIS Read-only'), findsOneWidget);
    expect(find.text('READ-ONLY'), findsOneWidget);
    expect(find.text('TRADING DISABLED'), findsOneWidget);
    expect(find.text('AVAILABLE CASH'), findsOneWidget);
    expect(find.text('₩30,000'), findsOneWidget);
    expect(find.textContaining('005930 ·'), findsOneWidget);
    expect(find.text('₩1,200,000'), findsWidgets);
    expect(find.text(r'$1,000.00'), findsNothing);

    controller.dispose();
  });

  testWidgets('Portfolio Snapshot shows KIS token expired warning',
      (tester) async {
    final controller =
        await _pumpSnapshot(tester, krSummary: _krTokenExpiredSummary);

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    expect(
      find.text(
          'KIS token expired. Portfolio data is unavailable until token refresh succeeds.'),
      findsOneWidget,
    );
    expect(
      find.text(
          'Token refresh is temporarily blocked until 2026-05-27T01:00:00+00:00.'),
      findsOneWidget,
    );
    expect(find.text('Unavailable'), findsOneWidget);
    expect(find.text('KIS positions unavailable'), findsOneWidget);
    expect(find.text('No open KR positions'), findsNothing);
    expect(find.text('??'), findsNothing);

    controller.dispose();
  });

  testWidgets('Portfolio Snapshot keeps cash when KIS positions fail',
      (tester) async {
    final controller =
        await _pumpSnapshot(tester, krSummary: _krCashOnlySummary);

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    expect(find.textContaining('30,000'), findsOneWidget);
    expect(find.text('Unavailable'), findsNothing);
    expect(find.text('KIS positions unavailable'), findsOneWidget);
    expect(find.text('No open KR positions'), findsNothing);

    controller.dispose();
  });

  testWidgets('Portfolio Snapshot keeps holdings when KIS balance fails',
      (tester) async {
    final controller =
        await _pumpSnapshot(tester, krSummary: _krPositionsOnlySummary);

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    expect(find.text('Unavailable'), findsOneWidget);
    expect(find.textContaining('005930'), findsOneWidget);
    expect(find.text('KIS positions unavailable'), findsNothing);
    expect(find.text('No open KR positions'), findsNothing);

    controller.dispose();
  });

  testWidgets('KIS portfolio profit percent uses cost basis and P/L amount',
      (tester) async {
    final controller =
        await _pumpSnapshot(tester, krSummary: _krSmallProfitSummary);

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    expect(find.text('₩9,867'), findsWidgets);
    expect(find.text('+₩37'), findsWidgets);
    expect(find.text('+0.38%'), findsNWidgets(2));
    expect(find.text('+37.00%'), findsNothing);
    expect(find.text('0.00%'), findsNothing);

    await _expandPositionCard(tester, '091810');
    expect(find.text('₩9,830'), findsWidgets);

    controller.dispose();
  });

  testWidgets('KIS negative P/L percent uses cost basis', (tester) async {
    final controller =
        await _pumpSnapshot(tester, krSummary: _krNegativeProfitSummary);

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    expect(find.text('-₩200'), findsWidgets);
    expect(find.text('-2.00%'), findsNWidgets(2));
    expect(find.text('-200.00%'), findsNothing);

    controller.dispose();
  });

  testWidgets('KIS missing cost basis displays safe percent fallback',
      (tester) async {
    final controller =
        await _pumpSnapshot(tester, krSummary: _krMissingCostSummary);

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    expect(find.text('₩9,867'), findsWidgets);
    expect(find.text('+₩37'), findsWidgets);
    expect(find.text('--'), findsNWidgets(2));
    expect(find.text('+37.00%'), findsNothing);

    controller.dispose();
  });

  testWidgets(
      'KIS managed position expands with detail and collapsed raw payload',
      (tester) async {
    final controller = await _pumpSnapshot(
      tester,
      krSummary: _krSummary,
      managedPositions: [_sellReadyManagedPosition],
      managementMode: true,
    );

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    expect(find.text('005930 · Samsung Electronics'), findsOneWidget);
    expect(find.text('SELL READY'), findsOneWidget);
    expect(find.text('Technical Snapshot'), findsNothing);
    expect(find.textContaining('raw_marker'), findsNothing);

    await _expandPositionCard(tester, '005930');

    expect(find.text('Technical Snapshot'), findsOneWidget);
    expect(find.text('SELL SCORE'), findsOneWidget);
    expect(find.text('Stop loss'), findsOneWidget);
    expect(find.text('Prepare Manual Sell Ticket'), findsOneWidget);
    expect(find.text('TICKET PREFILL ONLY'), findsWidgets);
    expect(
      find.text(
          'Ticket prefill does not validate, check confirm_live, or submit.'),
      findsOneWidget,
    );
    expect(find.text('Developer Raw Payload'), findsOneWidget);
    expect(find.textContaining('raw_marker'), findsNothing);

    controller.dispose();
  });

  testWidgets('Portfolio position card shows latest related event',
      (tester) async {
    final now = DateTime.now().toIso8601String();
    final controller = await _pumpSnapshot(
      tester,
      krSummary: _krSummary,
      managedPositions: [_takeProfitManagedPosition],
      managementMode: true,
      monitor: _monitorWithEvents([
        AutomationEvent(
          id: 'trigger-005930',
          timestamp: now,
          provider: 'kis',
          market: 'KR',
          category: 'trigger_detected',
          severity: 'warning',
          symbol: '005930',
          companyName: 'Samsung Electronics',
          action: 'sell',
          trigger: 'take_profit',
          result: 'blocked',
          reason: 'market_closed',
          blockReason: 'market_closed',
          orderId: null,
          brokerOrderId: null,
          kisOdno: null,
          realOrderSubmitted: false,
          brokerSubmitCalled: false,
          manualSubmitCalled: false,
          source: 'kis_scheduler_guarded_sell',
          mode: 'kis_scheduler_guarded_sell',
          triggerSource: 'scheduler',
          relatedRunId: 'run-1',
          relatedSignalId: null,
          relatedOrderId: null,
          developerPayload: const {},
        ),
      ]),
    );

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    await _expandPositionCard(tester, '005930');

    expect(find.text('Latest Event'), findsOneWidget);
    expect(find.text('Latest Scheduler Event'.toUpperCase()), findsOneWidget);
    expect(find.text('TAKE_PROFIT detected'), findsWidgets);
    expect(find.text('Trigger Today'), findsOneWidget);
    expect(find.text('yes'), findsWidgets);
    expect(find.text('Latest Block Reason'.toUpperCase()), findsOneWidget);
    expect(find.text('Block Reason'), findsOneWidget);
    expect(find.text('market_closed'), findsWidgets);

    controller.dispose();
  });

  testWidgets(
      'Portfolio position card warns when filled sell order conflicts with holdings',
      (tester) async {
    final controller = await _pumpSnapshot(
      tester,
      krSummary: _krSummary,
      managedPositions: [_sellReadyManagedPosition],
      managementMode: true,
      monitor: _monitorWithEvents(const [
        AutomationEvent(
          id: 'filled-005930',
          timestamp: '2026-05-28T02:00:00Z',
          provider: 'kis',
          market: 'KR',
          category: 'order_filled',
          severity: 'success',
          symbol: '005930',
          companyName: 'Samsung Electronics',
          action: 'sell',
          trigger: 'take_profit',
          result: 'FILLED',
          reason: 'FILLED',
          blockReason: null,
          orderId: '77',
          brokerOrderId: null,
          kisOdno: '0021651600',
          realOrderSubmitted: true,
          brokerSubmitCalled: true,
          manualSubmitCalled: false,
          source: 'kis_scheduler_guarded_sell',
          mode: 'kis_scheduler_guarded_sell',
          triggerSource: 'scheduler',
          relatedRunId: null,
          relatedSignalId: null,
          relatedOrderId: '77',
          developerPayload: {},
        ),
      ]),
    );

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    await _expandPositionCard(tester, '005930');

    expect(find.text('Position/order state may need sync'), findsOneWidget);
    expect(
      find.text(
          'Latest sell order appears filled, but the position still shows holdings.'),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('refresh-position-sync-005930')),
        findsOneWidget);
    expect(find.text('Refresh Positions'), findsWidgets);

    controller.dispose();
  });

  testWidgets('HOLD managed position does not show manual sell action',
      (tester) async {
    final controller = await _pumpSnapshot(
      tester,
      krSummary: _krSummary,
      managedPositions: [_holdManagedPosition],
      managementMode: true,
    );

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();
    await _expandPositionCard(tester, '005930');

    expect(find.text('HOLD'), findsWidgets);
    expect(find.text('Prepare Manual Sell Ticket'), findsNothing);

    controller.dispose();
  });

  testWidgets('Position card falls back when company name is missing',
      (tester) async {
    final controller = await _pumpSnapshot(
      tester,
      krSummary: _krMissingNameSummary,
      managementMode: true,
    );

    controller.selectedPortfolioMarket = PortfolioMarket.kr;
    controller.notifyListeners();
    await tester.pumpAndSettle();

    expect(find.text('091810'), findsOneWidget);
    expect(find.textContaining('091810 · 091810'), findsNothing);
    expect(find.textContaining('Unknown Company'), findsNothing);

    controller.dispose();
  });

  testWidgets('US portfolio percent display keeps raw decimal behavior',
      (tester) async {
    final controller =
        await _pumpSnapshot(tester, usSummary: _usPositionSummary);

    expect(find.text('US Portfolio / Alpaca Paper'), findsOneWidget);
    expect(find.text('AAPL - Apple Inc.'), findsOneWidget);
    expect(find.text(r'+$12.34'), findsWidgets);
    expect(find.text('+12.34%'), findsNWidgets(2));

    controller.dispose();
  });

  testWidgets('US position title falls back to symbol without duplication',
      (tester) async {
    final controller =
        await _pumpSnapshot(tester, usSummary: _usSymbolFallbackSummary);

    expect(find.text('US Portfolio / Alpaca Paper'), findsOneWidget);
    expect(find.text('AAPL'), findsOneWidget);
    expect(find.textContaining('AAPL - AAPL'), findsNothing);
    expect(find.textContaining('Unknown Company'), findsNothing);

    controller.dispose();
  });
}

class _NoopApiClient extends ApiClient {
  _NoopApiClient({
    this.usSummary = _usSummary,
    this.krSummary = _krSummary,
  });

  final PortfolioSummary usSummary;
  final PortfolioSummary krSummary;

  @override
  Future<PortfolioSummary> fetchPortfolioSummary() async => usSummary;

  @override
  Future<PortfolioSummary> fetchUsPortfolioSummary() async => usSummary;

  @override
  Future<PortfolioSummary> fetchKrPortfolioSummary() async => krSummary;

  @override
  Future<PortfolioSummary> fetchPortfolioSummaryForMarket(String market) {
    return market.trim().toUpperCase() == 'KR'
        ? fetchKrPortfolioSummary()
        : fetchUsPortfolioSummary();
  }
}

Future<DashboardController> _pumpSnapshot(
  WidgetTester tester, {
  PortfolioSummary usSummary = _usSummary,
  PortfolioSummary krSummary = _krSummary,
  List<ManagedPosition> managedPositions = const [],
  bool managementMode = false,
  AutomationRuntimeMonitor? monitor,
}) async {
  final controller = DashboardController(
    _NoopApiClient(usSummary: usSummary, krSummary: krSummary),
    autoload: false,
  )
    ..usPortfolioSummary = usSummary
    ..krPortfolioSummary = krSummary
    ..kisManagedPositions = managedPositions
    ..automationRuntimeMonitor = monitor;

  await tester.pumpWidget(MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => PortfolioSnapshotSection(
            controller: controller,
            managementMode: managementMode,
          ),
        ),
      ),
    ),
  ));
  return controller;
}

Future<void> _expandPositionCard(WidgetTester tester, String symbol) async {
  final card = find.byKey(ValueKey('portfolio-position-card-$symbol'));
  expect(card, findsOneWidget);
  await tester.ensureVisible(card);
  await tester.pumpAndSettle();
  await tester.tap(card);
  await tester.pumpAndSettle();
}

AutomationRuntimeMonitor _monitorWithEvents(List<AutomationEvent> events) {
  return AutomationRuntimeMonitor(
    readOnly: true,
    global: const GlobalAutomationStatus(
      botEnabled: false,
      dryRun: true,
      killSwitch: false,
      schedulerEnabled: false,
      selectedProvider: 'KIS / KR',
      currentLocalTime: '2026-05-28T12:00:00+09:00',
      lastRefreshTime: '2026-05-28T12:01:00+09:00',
    ),
    alpaca: const ProviderAutomationStatus(
      provider: 'Alpaca',
      market: 'US',
      schedulerEnabled: false,
      botEnabled: false,
      dryRun: true,
      paperMode: true,
      nextSlotName: null,
      nextSlotTimeLocal: null,
      lastRunAt: null,
      lastResult: null,
      lastSymbol: null,
      lastAction: null,
      lastBlockReason: null,
      lastRunId: null,
      orderSubmitted: false,
      orderId: null,
      mode: '',
      lastSingleRunAt: null,
      lastSingleSymbol: null,
      lastSingleAction: null,
      lastSingleResult: null,
      lastSingleBlockReason: null,
      todayPaperOrderCount: 0,
    ),
    kis: const KisAutomationStatus(
      schedulerEnabled: false,
      schedulerConfigEnabled: false,
      schedulerDryRun: true,
      schedulerAllowRealOrders: false,
      realOrderSchedulerEnabled: false,
      liveSchedulerReady: false,
      schedulerBuyEnabled: false,
      schedulerSellEnabled: false,
      schedulerAllowLimitedAutoBuy: false,
      schedulerAllowLimitedAutoSell: false,
      liveAutoBuyEnabled: false,
      liveAutoSellEnabled: false,
      stopLossEnabled: false,
      takeProfitEnabled: false,
      limitedAutoBuyEnabled: false,
      schedulerStatus: null,
      guardedSell: null,
      guardedBuy: null,
      nextSlotName: null,
      nextSlotTimeLocal: null,
      lastSchedulerRunAt: null,
      lastSchedulerRunResult: null,
      lastSchedulerRunReason: null,
      lastSchedulerRunId: null,
      lastSchedulerRunMode: null,
      lastSchedulerRunTriggerSource: null,
      lastSellRunAt: null,
      lastBuyRunAt: null,
      lastSellRunResult: null,
      lastBuyRunResult: null,
      lastTriggerDetected: 'none',
      lastBlockReason: null,
      blockReasons: [],
      realOrderSubmitted: false,
      brokerSubmitCalled: false,
      manualSubmitCalled: false,
      kisOdno: null,
      orderId: null,
      todaySubmittedCount: null,
      dailyLimitMax: null,
      dailyLimitRemaining: null,
    ),
    lastRuns: const [],
    lastOrders: const [],
    lastSignals: const [],
    events: events,
    warnings: const [],
    diagnostics: const {},
  );
}

const _usSummary = PortfolioSummary(
  currency: 'USD',
  positionsCount: 0,
  pendingOrdersCount: 0,
  totalCostBasis: 800,
  totalMarketValue: 1000,
  totalUnrealizedPl: 200,
  totalUnrealizedPlpc: 0.25,
  cash: 123.45,
  positions: [],
  pendingOrders: [],
);

const _usPositionSummary = PortfolioSummary(
  currency: 'USD',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 100,
  totalMarketValue: 112.34,
  totalUnrealizedPl: 12.34,
  totalUnrealizedPlpc: 0.1234,
  cash: 123.45,
  positions: [
    PositionSummary(
      symbol: 'AAPL',
      name: 'Apple Inc.',
      broker: 'alpaca',
      market: 'US',
      side: 'long',
      qty: 1,
      avgEntryPrice: 100,
      costBasis: 100,
      currentPrice: 112.34,
      marketValue: 112.34,
      unrealizedPl: 12.34,
      unrealizedPlpc: 0.1234,
    ),
  ],
  pendingOrders: [],
);

const _usSymbolFallbackSummary = PortfolioSummary(
  currency: 'USD',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 100,
  totalMarketValue: 112.34,
  totalUnrealizedPl: 12.34,
  totalUnrealizedPlpc: 0.1234,
  cash: 123.45,
  positions: [
    PositionSummary(
      symbol: 'AAPL',
      name: 'AAPL',
      broker: 'alpaca',
      market: 'US',
      side: 'long',
      qty: 1,
      avgEntryPrice: 100,
      costBasis: 100,
      currentPrice: 112.34,
      marketValue: 112.34,
      unrealizedPl: 12.34,
      unrealizedPlpc: 0.1234,
    ),
  ],
  pendingOrders: [],
);

const _krSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 1,
  totalCostBasis: 1000000,
  totalMarketValue: 1200000,
  totalUnrealizedPl: 200000,
  totalUnrealizedPlpc: 0.2,
  cash: 30000,
  positions: [
    PositionSummary(
      symbol: '005930',
      name: '?쇱꽦?꾩옄',
      side: 'long',
      qty: 2,
      avgEntryPrice: 500000,
      costBasis: 1000000,
      currentPrice: 600000,
      marketValue: 1200000,
      unrealizedPl: 200000,
      unrealizedPlpc: 0.2,
    ),
  ],
  pendingOrders: [
    PendingOrderSummary(
      id: 'order-1',
      symbol: '005930',
      name: '?쇱꽦?꾩옄',
      side: 'buy',
      type: '',
      status: 'pending',
      qty: 1,
      unfilledQty: 1,
      notional: null,
      limitPrice: null,
      price: 600000,
      estimatedAmount: 600000,
      submittedAt: '09:30:00',
    ),
  ],
);

const _krTokenExpiredSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 0,
  pendingOrdersCount: 0,
  totalCostBasis: 0,
  totalMarketValue: 0,
  totalUnrealizedPl: 0,
  totalUnrealizedPlpc: 0,
  cash: 0,
  positions: [],
  pendingOrders: [],
  cashKnown: false,
  balanceUnavailable: true,
  positionsUnavailable: true,
  openOrdersUnavailable: true,
  kisAuthErrorMessage:
      'KIS token expired. Portfolio data is unavailable until token refresh succeeds.',
  nextRefreshAllowedAt: '2026-05-27T01:00:00+00:00',
  tokenExpired: true,
);

const _krCashOnlySummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 0,
  pendingOrdersCount: 0,
  totalCostBasis: 0,
  totalMarketValue: 0,
  totalUnrealizedPl: 0,
  totalUnrealizedPlpc: 0,
  cash: 30000,
  positions: [],
  pendingOrders: [],
  positionsUnavailable: true,
);

const _krPositionsOnlySummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 1000000,
  totalMarketValue: 1200000,
  totalUnrealizedPl: 200000,
  totalUnrealizedPlpc: 0.2,
  cash: 0,
  positions: [
    PositionSummary(
      symbol: '005930',
      name: '??깃쉐?袁⑹쁽',
      side: 'long',
      qty: 2,
      avgEntryPrice: 500000,
      costBasis: 1000000,
      currentPrice: 600000,
      marketValue: 1200000,
      unrealizedPl: 200000,
      unrealizedPlpc: 0.2,
    ),
  ],
  pendingOrders: [],
  cashKnown: false,
  balanceUnavailable: true,
);

const _krSmallProfitSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 9830,
  totalMarketValue: 9867,
  totalUnrealizedPl: 37,
  totalUnrealizedPlpc: 0,
  cash: 30000,
  positions: [
    PositionSummary(
      symbol: '091810',
      name: 'Small Profit',
      side: 'long',
      qty: 11,
      avgEntryPrice: 893.64,
      costBasis: 9830,
      currentPrice: 897,
      marketValue: 9867,
      unrealizedPl: 37,
      unrealizedPlpc: 37,
    ),
  ],
  pendingOrders: [],
);

const _krNegativeProfitSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 10000,
  totalMarketValue: 9800,
  totalUnrealizedPl: -200,
  totalUnrealizedPlpc: 0,
  cash: 30000,
  positions: [
    PositionSummary(
      symbol: '091810',
      name: 'Small Loss',
      side: 'long',
      qty: 10,
      avgEntryPrice: 1000,
      costBasis: 10000,
      currentPrice: 980,
      marketValue: 9800,
      unrealizedPl: -200,
      unrealizedPlpc: -200,
    ),
  ],
  pendingOrders: [],
);

const _krMissingCostSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 0,
  totalMarketValue: 9867,
  totalUnrealizedPl: 37,
  totalUnrealizedPlpc: 37,
  cash: 30000,
  positions: [
    PositionSummary(
      symbol: '091810',
      name: 'Missing Cost',
      side: 'long',
      qty: 11,
      avgEntryPrice: 0,
      costBasis: 0,
      currentPrice: 897,
      marketValue: 9867,
      unrealizedPl: 37,
      unrealizedPlpc: 37,
    ),
  ],
  pendingOrders: [],
);

const _krMissingNameSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 10000,
  totalMarketValue: 9800,
  totalUnrealizedPl: -200,
  totalUnrealizedPlpc: 0,
  cash: 30000,
  positions: [
    PositionSummary(
      symbol: '091810',
      name: '',
      side: 'long',
      qty: 10,
      avgEntryPrice: 1000,
      costBasis: 10000,
      currentPrice: 980,
      marketValue: 9800,
      unrealizedPl: -200,
      unrealizedPlpc: -200,
    ),
  ],
  pendingOrders: [],
);

final _sellReadyManagedPosition = ManagedPosition.fromJson({
  'provider': 'kis',
  'market': 'KR',
  'symbol': '005930',
  'company_name': 'Samsung Electronics',
  'quantity': 2,
  'average_price': 500000,
  'cost_basis': 1000000,
  'current_price': 600000,
  'current_value': 1200000,
  'unrealized_pl': 200000,
  'unrealized_pl_pct': 0.2,
  'holding_status': 'SELL_READY',
  'exit_reason': 'stop_loss_triggered',
  'human_reason': 'Stop-loss threshold reached.',
  'stop_loss_triggered': true,
  'final_sell_score': 72,
  'final_buy_score': 18,
  'technical_snapshot': {
    'indicator_status': 'ok',
    'indicator_bar_count': 100,
    'ema20': 610000,
    'price_vs_ema20': 'below',
    'ema50': 620000,
    'price_vs_ema50': 'below',
    'vwap': 615000,
    'price_vs_vwap': 'below',
    'rsi': 31,
    'atr': 1200,
    'volume_ratio': 1.2,
    'momentum': -0.03,
    'recent_return': -0.05,
  },
  'risk_flags': ['stop_loss_triggered'],
  'gating_notes': ['Manual sell must use existing submit path.'],
  'block_reasons': [],
  'can_prepare_manual_sell': true,
  'can_submit_manual_sell': true,
  'raw_marker': 'raw payload hidden until expanded',
});

final _takeProfitManagedPosition = ManagedPosition.fromJson({
  'provider': 'kis',
  'market': 'KR',
  'symbol': '005930',
  'company_name': 'Samsung Electronics',
  'quantity': 2,
  'average_price': 500000,
  'cost_basis': 1000000,
  'current_price': 600000,
  'current_value': 1200000,
  'unrealized_pl': 200000,
  'unrealized_pl_pct': 0.2,
  'holding_status': 'SELL_READY',
  'exit_reason': 'take_profit_triggered',
  'human_reason': 'Take-profit threshold reached.',
  'take_profit_triggered': true,
  'technical_snapshot': {},
  'risk_flags': ['take_profit_triggered'],
  'gating_notes': [],
  'block_reasons': [],
  'can_prepare_manual_sell': true,
  'can_submit_manual_sell': true,
});

final _holdManagedPosition = ManagedPosition.fromJson({
  'provider': 'kis',
  'market': 'KR',
  'symbol': '005930',
  'company_name': 'Samsung Electronics',
  'quantity': 2,
  'current_price': 600000,
  'current_value': 1200000,
  'unrealized_pl': 200000,
  'unrealized_pl_pct': 0.2,
  'holding_status': 'HOLD',
  'exit_reason': 'no_exit_condition',
  'human_reason': 'No sell trigger detected.',
  'technical_snapshot': {},
  'risk_flags': [],
  'gating_notes': [],
  'block_reasons': [],
  'can_prepare_manual_sell': true,
  'can_submit_manual_sell': true,
});
