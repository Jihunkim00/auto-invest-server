import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_screen.dart';
import 'package:auto_invest_dashboard/features/dashboard/manual_order_screen.dart';
import 'package:auto_invest_dashboard/models/automation_runtime_monitor.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_buy.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_sell.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/managed_position.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';
import 'package:auto_invest_dashboard/models/scheduler_status.dart';

class FakeKisApiClient extends ApiClient {
  int fetchRecentRunsCalls = 0;

  @override
  Future<OpsSettings> getOpsSettings() async {
    return const OpsSettings(
      schedulerEnabled: true,
      botEnabled: true,
      dryRun: true,
      killSwitch: false,
      brokerMode: 'Paper',
      defaultGateLevel: 2,
      maxDailyTrades: 5,
      maxDailyEntries: 2,
      minEntryScore: 65,
      minScoreGap: 3,
    );
  }

  @override
  Future<SchedulerStatus> fetchSchedulerStatus() async {
    return const SchedulerStatus(
      runtimeSchedulerEnabled: true,
      us: MarketSchedulerStatus(
        enabledForScheduler: true,
        timezone: 'America/New_York',
        slots: [],
      ),
      kr: MarketSchedulerStatus(
        enabledForScheduler: true,
        timezone: 'Asia/Seoul',
        slots: [],
        previewOnly: true,
        realOrdersAllowed: false,
      ),
    );
  }

  @override
  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async {
    return KisSchedulerSimulationStatus.safeDefault();
  }

  @override
  Future<List<TradingLogItem>> fetchRecentRuns({int limit = 20}) async {
    fetchRecentRunsCalls += 1;
    return const [
      TradingLogItem(
        id: 1,
        runKey: 'alpaca-run',
        provider: 'alpaca',
        market: 'US',
        symbol: 'AAPL',
        triggerSource: 'scheduler',
        mode: 'watchlist_run',
        action: 'hold',
        result: 'skipped',
        reason: 'weak_final_score_gap',
        relatedOrderId: null,
        createdAt: '2026-05-28T01:00:00Z',
        gateLevel: 2,
      ),
    ];
  }

  @override
  Future<List<OrderLogItem>> fetchRecentOrders({int limit = 20}) async {
    return const [];
  }

  @override
  Future<List<SignalLogItem>> fetchRecentSignals({int limit = 20}) async {
    return const [];
  }

  @override
  Future<KisSchedulerGuardedSellResult>
      fetchKisSchedulerGuardedSellStatus() async {
    return KisSchedulerGuardedSellResult.fromJson({
      'status': 'ok',
      'result': 'blocked',
      'action': 'sell',
      'reason': 'market_closed',
      'trigger': 'take_profit',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    });
  }

  @override
  Future<KisSchedulerGuardedBuyResult>
      fetchKisSchedulerGuardedBuyStatus() async {
    return KisSchedulerGuardedBuyResult.fromJson({
      'status': 'ok',
      'result': 'blocked',
      'action': 'hold',
      'reason': 'scheduler_buy_disabled',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    });
  }

  @override
  Future<ManualSellPreparation> prepareKisManualSell(String symbol) async {
    return const ManualSellPreparation(
      provider: 'kis',
      market: 'KR',
      symbol: '005930',
      companyName: 'Samsung Electronics',
      quantity: 1,
      currentPrice: 600000,
      estimatedAmount: 600000,
      exitReason: 'stop_loss_triggered',
      humanReason: 'Stop loss triggered',
      holdingStatus: 'SELL_READY',
      canPrepare: true,
      canSubmit: true,
      blockReasons: [],
      sourceMetadata: {'source': 'portfolio_position'},
      rawPayload: {'symbol': '005930'},
    );
  }
}

const _krManagedPosition = ManagedPosition(
  provider: 'kis',
  market: 'KR',
  symbol: '005930',
  companyName: 'Samsung Electronics',
  quantity: 1,
  averagePrice: 500000,
  costBasis: 1000000,
  currentPrice: 600000,
  currentValue: 1200000,
  unrealizedPl: 200000,
  unrealizedPlPct: 0.20,
  holdingStatus: 'SELL_READY',
  exitReason: 'stop_loss_triggered',
  humanReason: 'Stop loss triggered',
  stopLossTriggered: true,
  takeProfitTriggered: false,
  weakTrendTriggered: false,
  sellPressureTriggered: false,
  manualReviewRequired: true,
  finalSellScore: 73.5,
  finalBuyScore: 10.1,
  quantSellScore: 80.0,
  quantBuyScore: 18.2,
  aiSellScore: 75.0,
  aiBuyScore: 5.0,
  confidence: 92.0,
  technicalSnapshot: {},
  riskFlags: [],
  gatingNotes: [],
  blockReasons: [],
  canPrepareManualSell: true,
  canSubmitManualSell: true,
  latestManualSellOrder: null,
  rawPayload: {},
);

void main() {
  testWidgets('Automation Runtime Monitor renders global safety',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor()
      ..selectedProvider = SelectedProvider.alpaca;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    expect(find.text('Automation Runtime Monitor'), findsOneWidget);
    expect(find.text('Global Safety'), findsOneWidget);
    expect(find.text('DRY RUN ON'), findsOneWidget);
    expect(find.text('Kill Switch OFF'), findsOneWidget);
    expect(find.text('Scheduler ON'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Automation Runtime Monitor renders Alpaca and KIS status',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor()
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    expect(find.text('Alpaca Paper Scheduler'), findsOneWidget);
    expect(find.textContaining('weak_final_score_gap'), findsWidgets);
    expect(find.text('KIS Live Scheduler'), findsOneWidget);
    expect(find.text('TAKE_PROFIT'), findsWidgets);
    expect(find.text('REAL ORDER SUBMITTED'), findsOneWidget);
    expect(find.text('false'), findsWidgets);
    expect(find.textContaining('market_closed'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Automation Runtime Monitor refresh button calls controller path',
      (tester) async {
    final api = FakeKisApiClient();
    final controller = DashboardController(api, autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor();

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await tester.tap(find.byKey(const ValueKey('automation-runtime-refresh')));
    await tester.pumpAndSettle();

    expect(api.fetchRecentRunsCalls, 1);
    expect(controller.automationRuntimeMonitor?.alpaca.lastResult, 'skipped');

    controller.dispose();
  });

  testWidgets('Home dashboard includes Portfolio Snapshot and holdings',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..usPortfolioSummary = _usSummary
      ..krPortfolioSummary = _krSummary
      ..kisManagedPositions = const [_krManagedPosition]
      ..selectedProvider = SelectedProvider.kis
      ..selectedPortfolioMarket = PortfolioMarket.kr;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => DashboardScreen(
            controller: controller,
            onOpenManualOrder: () {},
            onReviewPosition: () {},
          ),
        ),
      ),
    ));

    expect(find.text('Portfolio Snapshot'), findsOneWidget);
    expect(find.text('Current Holdings'), findsOneWidget);
    expect(find.byKey(const ValueKey('portfolio-position-card-005930')),
        findsOneWidget);
    expect(find.textContaining('005930 · Samsung Electronics'), findsOneWidget);
    expect(find.textContaining('Samsung Electronics'), findsOneWidget);
  });

  testWidgets(
      'Prepare Sell Ticket on Home portfolio pre-fills manual order only',
      (tester) async {
    var openedManualOrder = false;
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..usPortfolioSummary = _usSummary
      ..krPortfolioSummary = _krSummary
      ..kisManagedPositions = const [_krManagedPosition]
      ..selectedProvider = SelectedProvider.kis
      ..selectedPortfolioMarket = PortfolioMarket.kr;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => DashboardScreen(
            controller: controller,
            onOpenManualOrder: () => openedManualOrder = true,
            onReviewPosition: () {},
          ),
        ),
      ),
    ));

    await tester.ensureVisible(
      find.textContaining('005930 · Samsung Electronics'),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.textContaining('005930 · Samsung Electronics'));
    await tester.pumpAndSettle();

    final prepareSellButton =
        find.byKey(const ValueKey('prepare-manual-sell-005930'));
    await tester.ensureVisible(prepareSellButton);
    await tester.pumpAndSettle();

    expect(prepareSellButton, findsOneWidget);
    await tester.tap(prepareSellButton);
    await tester.pumpAndSettle();

    expect(openedManualOrder, isTrue);
    expect(controller.selectedOrderMarket, PortfolioMarket.kr);
    expect(controller.orderTicketSide, 'sell');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(controller.orderValidationError, isNull);
    expect(
        controller.orderTicketSourceMetadata?['source'], 'portfolio_position');
  });

  testWidgets('Trading shows a prepared KIS manual sell ticket',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..kisManagedPositions = const [_krManagedPosition];

    final result = await controller.prepareKisManualSellFromManagedPosition(
      _krManagedPosition,
    );
    expect(result.success, isTrue);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => TradingScreen(controller: controller),
        ),
      ),
    ));

    expect(find.text('Single Symbol Analyze & Buy'), findsOneWidget);
    expect(find.text('KIS Manual Buy/Sell Ticket'), findsOneWidget);
    expect(find.text('KIS Manual SELL Ticket'), findsOneWidget);
    expect(find.text('Prepared Manual Sell'), findsOneWidget);
    expect(find.text('SELL'), findsWidgets);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('Validate Sell'), findsOneWidget);
    expect(find.text('Submit Manual Sell'), findsOneWidget);
    expect(controller.kisLiveConfirmation, isFalse);

    controller.dispose();
  });
}

const _usSummary = PortfolioSummary(
  currency: 'USD',
  positionsCount: 0,
  pendingOrdersCount: 0,
  totalCostBasis: 1000,
  totalMarketValue: 1200,
  totalUnrealizedPl: 200,
  totalUnrealizedPlpc: 0.20,
  cash: 500,
  positions: [],
  pendingOrders: [],
);

const _krSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 1000000,
  totalMarketValue: 1200000,
  totalUnrealizedPl: 200000,
  totalUnrealizedPlpc: 0.20,
  cash: 30000,
  positions: [
    PositionSummary(
      symbol: '005930',
      name: '삼성전자',
      side: 'long',
      qty: 2,
      avgEntryPrice: 500000,
      costBasis: 1000000,
      currentPrice: 600000,
      marketValue: 1200000,
      unrealizedPl: 200000,
      unrealizedPlpc: 0.20,
    ),
  ],
  pendingOrders: [],
);

AutomationRuntimeMonitor _runtimeMonitor() {
  return AutomationRuntimeMonitor.fromSources(
    settings: const OpsSettings(
      schedulerEnabled: true,
      botEnabled: true,
      dryRun: true,
      killSwitch: false,
      brokerMode: 'Paper',
      defaultGateLevel: 2,
      maxDailyTrades: 5,
      maxDailyEntries: 2,
      minEntryScore: 65,
      minScoreGap: 3,
      kisSchedulerEnabled: true,
      kisSchedulerDryRun: true,
      kisSchedulerAllowRealOrders: false,
      kisSchedulerBuyEnabled: false,
      kisSchedulerSellEnabled: true,
      kisLiveAutoBuyEnabled: false,
      kisLiveAutoSellEnabled: false,
      kisLimitedAutoStopLossEnabled: true,
      kisLimitedAutoTakeProfitEnabled: true,
    ),
    schedulerStatus: const SchedulerStatus(
      runtimeSchedulerEnabled: true,
      us: MarketSchedulerStatus(
        enabledForScheduler: true,
        timezone: 'America/New_York',
        slots: [],
      ),
      kr: MarketSchedulerStatus(
        enabledForScheduler: true,
        timezone: 'Asia/Seoul',
        slots: [],
        previewOnly: true,
        realOrdersAllowed: false,
      ),
    ),
    selectedProvider: 'KIS / KR',
    currentLocalTime: '2026-05-28T12:00:00+09:00',
    lastRefreshTime: '2026-05-28T12:01:00+09:00',
    kisSchedulerStatus: KisSchedulerSimulationStatus.safeDefault(),
    guardedSell: KisSchedulerGuardedSellResult.fromJson({
      'status': 'ok',
      'result': 'blocked',
      'action': 'sell',
      'reason': 'market_closed',
      'primary_block_reason': 'market_closed',
      'trigger': 'take_profit',
      'symbol': '005930',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'daily_limit': {
        'today_submitted_count': 0,
        'max_live_orders_per_day': 2,
        'remaining': 2,
      },
      'created_at': '2026-05-28T02:30:00Z',
    }),
    guardedBuy: KisSchedulerGuardedBuyResult.fromJson({
      'status': 'ok',
      'result': 'blocked',
      'action': 'hold',
      'reason': 'scheduler_buy_disabled',
      'primary_block_reason': 'scheduler_buy_disabled',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'created_at': '2026-05-28T02:31:00Z',
    }),
    runs: const [
      TradingLogItem(
        id: 1,
        runKey: 'alpaca-run',
        provider: 'alpaca',
        market: 'US',
        symbol: 'AAPL',
        triggerSource: 'scheduler',
        mode: 'watchlist_run',
        action: 'hold',
        result: 'skipped',
        reason: 'weak_final_score_gap',
        relatedOrderId: null,
        createdAt: '2026-05-28T01:00:00Z',
        gateLevel: 2,
      ),
      TradingLogItem(
        id: 2,
        runKey: 'kis-sell',
        provider: 'kis',
        market: 'KR',
        symbol: '005930',
        triggerSource: 'scheduler_guarded_sell',
        mode: 'kis_scheduler_guarded_sell',
        action: 'sell',
        result: 'blocked',
        reason: 'market_closed',
        relatedOrderId: null,
        createdAt: '2026-05-28T02:30:00Z',
        gateLevel: 2,
        exitTrigger: 'take_profit',
      ),
    ],
  );
}
