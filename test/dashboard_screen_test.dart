import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_screen.dart';
import 'package:auto_invest_dashboard/features/dashboard/manual_order_screen.dart';
import 'package:auto_invest_dashboard/models/automation_runtime_monitor.dart';
import 'package:auto_invest_dashboard/models/kis_live_exit_preflight.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_dry_run_orchestration.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_buy.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_sell.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/managed_position.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';
import 'package:auto_invest_dashboard/models/scheduler_status.dart';
import 'package:auto_invest_dashboard/models/strategy_profile.dart';
import 'package:auto_invest_dashboard/models/watchlist_run_result.dart';

class FakeKisApiClient extends ApiClient {
  int fetchRecentRunsCalls = 0;
  int guardedSellStatusCalls = 0;
  int guardedBuyStatusCalls = 0;
  int dryRunOrchestrationCalls = 0;
  int guardedSellRunCalls = 0;
  int guardedBuyRunCalls = 0;
  int alpacaWatchlistCalls = 0;
  int liveExitPreflightCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;
  String? lastWatchlistProvider;

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
  Future<StrategyProfileList> fetchStrategyProfiles() async =>
      _safeStrategyProfileList();

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
    guardedSellStatusCalls += 1;
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
    guardedBuyStatusCalls += 1;
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
  Future<KisSchedulerDryRunOrchestration>
      runKisSchedulerDryRunOrchestrationOnce({
    String? slotLabel,
    bool includeBuy = true,
    bool includeSell = true,
    bool includeRaw = false,
  }) async {
    dryRunOrchestrationCalls += 1;
    return KisSchedulerDryRunOrchestration.fromJson({
      'provider': 'kis',
      'market': 'KR',
      'mode': 'kis_scheduler_dry_run_orchestration',
      'trigger_source': 'scheduler_dry_run_orchestration',
      'slot_label': slotLabel ?? 'manual_dry_run',
      'result': 'blocked',
      'readiness_only': true,
      'dry_run': true,
      'scheduler_real_orders_enabled': false,
      'real_order_submit_allowed': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'summary': {
        'modules_requested': ['sell', 'buy'],
        'modules_completed': ['sell', 'buy'],
        'modules_blocked': [],
        'sell_candidates_reviewed': 1,
        'buy_candidates_reviewed': 0,
        'sell_ready_count': 0,
        'buy_ready_count': 0,
        'submitted_order_count': 0,
        'broker_submit_count': 0,
        'manual_submit_count': 0,
        'real_order_submit_allowed': false,
        'primary_block_reason': 'dry_run_only',
      },
      'child_runs': [],
      'safety': {
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      },
      'diagnostics': {},
    });
  }

  @override
  Future<KisSchedulerGuardedSellResult> runKisSchedulerGuardedSellOnce({
    String? slotLabel,
    bool includeRaw = false,
    String triggerSource = 'scheduler_manual_test',
  }) async {
    guardedSellRunCalls += 1;
    return fetchKisSchedulerGuardedSellStatus();
  }

  @override
  Future<KisSchedulerGuardedBuyResult> runKisSchedulerGuardedBuyOnce({
    String? slotLabel,
    bool includeRaw = false,
    String triggerSource = 'scheduler_manual_test',
  }) async {
    guardedBuyRunCalls += 1;
    return fetchKisSchedulerGuardedBuyStatus();
  }

  @override
  Future<WatchlistRunResult> runWatchlistForProvider({
    required String provider,
    required int gateLevel,
  }) async {
    lastWatchlistProvider = provider;
    if (provider.trim().toLowerCase() == 'alpaca') {
      alpacaWatchlistCalls += 1;
    }
    return const WatchlistRunResult(
      configuredSymbolCount: 1,
      analyzedSymbolCount: 1,
      quantCandidatesCount: 1,
      researchedCandidatesCount: 1,
      finalBestCandidate: 'AAPL',
      secondFinalCandidate: '',
      tiedFinalCandidates: [],
      nearTiedCandidates: [],
      tieBreakerApplied: false,
      finalCandidateSelectionReason: 'paper check',
      bestScore: 62,
      finalScoreGap: 1,
      minEntryScore: 65,
      minScoreGap: 3,
      shouldTrade: false,
      triggeredSymbol: null,
      triggerBlockReason: 'weak_final_score_gap',
      finalEntryReady: false,
      finalActionHint: 'watch',
      action: 'hold',
      orderId: null,
      topQuantCandidates: [],
      researchedCandidates: [],
      finalRankedCandidates: [],
      result: 'skipped',
      reason: 'weak_final_score_gap',
      triggerSource: 'manual',
    );
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

  @override
  Future<KisLiveExitPreflightResult> runKisLiveExitPreflight() async {
    liveExitPreflightCalls += 1;
    return KisLiveExitPreflightResult.fromJson(_liveExitPreflightJson());
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
    throw const ApiRequestException('validation should not run');
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
    throw const ApiRequestException('submit should not run');
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
  testWidgets('Operational Readiness card renders current mode',
      (tester) async {
    final controller = _operationalController(
      status: _operationalStatus(mode: 'dry_run_simulation'),
    );

    await _pumpOperationalReadiness(tester, controller);

    expect(find.byKey(const Key('operational-readiness-card')), findsOneWidget);
    expect(find.text('Operational Readiness'), findsOneWidget);
    expect(
        find.text('Dry-run Simulation (dry_run_simulation)'), findsOneWidget);
    expect(find.text('Warning'), findsOneWidget);
    expect(find.text('safe'), findsWidgets);

    controller.dispose();
  });

  testWidgets(
      'Operational Readiness Safe Mode renders SAFE without live badges',
      (tester) async {
    final controller = _operationalController(
      status: _operationalStatus(mode: 'safe_mode'),
    );

    await _pumpOperationalReadiness(tester, controller);

    expect(find.text('SAFE'), findsOneWidget);
    expect(find.text('LIVE BUY ARMED'), findsNothing);
    expect(find.text('LIVE SELL ARMED'), findsNothing);
    expect(find.text('Live buy armed'), findsOneWidget);
    expect(find.text('Live sell armed'), findsOneWidget);
    expect(find.text('NO'), findsWidgets);

    controller.dispose();
  });

  testWidgets(
      'Operational Readiness KIS Sell-only mode renders sell-only and buy off',
      (tester) async {
    final controller = _operationalController(
      status: _operationalStatus(mode: 'kis_sell_only_automation'),
    );

    await _pumpOperationalReadiness(tester, controller);

    expect(find.text('SELL ONLY ARMED'), findsWidgets);
    expect(find.text('LIVE SELL ARMED'), findsOneWidget);
    expect(find.text('LIVE BUY ARMED'), findsNothing);
    expect(find.text('Live buy armed'), findsOneWidget);
    expect(find.text('NO'), findsWidgets);

    controller.dispose();
  });

  testWidgets(
      'Operational Readiness Full Live Test mode renders danger and both live badges',
      (tester) async {
    final controller = _operationalController(
      status: _operationalStatus(mode: 'full_live_test_mode'),
    );

    await _pumpOperationalReadiness(tester, controller);

    expect(find.text('DANGEROUS FULL LIVE'), findsWidgets);
    expect(find.text('LIVE BUY ARMED'), findsOneWidget);
    expect(find.text('LIVE SELL ARMED'), findsOneWidget);
    expect(find.byKey(const ValueKey('operational-switch-safe-mode')),
        findsOneWidget);

    controller.dispose();
  });

  testWidgets(
      'Operational Readiness renders global safety and market schedules',
      (tester) async {
    final controller = _operationalController(
      status: _operationalStatus(
        mode: 'kis_sell_only_automation',
        dailyRemaining: 2,
        killSwitch: true,
        usNoNewEntryAfter: '15:45',
        krNoNewEntryAfter: '14:40',
      ),
    );

    await _pumpOperationalReadiness(tester, controller);

    expect(find.text('Global Safety'), findsOneWidget);
    expect(find.text('Scheduler'), findsWidgets);
    expect(find.text('Dry-run'), findsOneWidget);
    expect(find.text('Kill switch'), findsOneWidget);
    expect(find.text('Alpaca / US'), findsOneWidget);
    expect(find.text('open_phase 2026-06-11T09:30 ET'), findsOneWidget);
    expect(find.text('15:45 ET'), findsOneWidget);
    expect(find.text('KIS / KR'), findsOneWidget);
    expect(find.text('midday 2026-06-12T11:30 KST'), findsOneWidget);
    expect(find.text('14:40 KST'), findsOneWidget);
    expect(find.text('Daily remaining'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);

    controller.dispose();
  });

  testWidgets(
      'Operational Readiness backend failure shows unavailable and Retry',
      (tester) async {
    final api = _OperationalReadinessApiClient(
      status: _operationalStatus(mode: 'safe_mode'),
    );
    final controller = _operationalController(
      api: api,
      status: _operationalStatus(mode: 'safe_mode'),
    )
      ..schedulerStatusLoaded = false
      ..schedulerStatusError = 'Operational readiness unavailable: offline';

    await _pumpOperationalReadiness(tester, controller);

    expect(find.text('Operational readiness unavailable.'), findsOneWidget);
    expect(find.byKey(const ValueKey('operational-readiness-retry')),
        findsOneWidget);

    final retry = find.byKey(const ValueKey('operational-readiness-retry'));
    await _showDashboardFinder(tester, retry);
    await tester.tap(retry);
    await tester.pumpAndSettle();

    expect(api.fetchSchedulerStatusCalls, 1);
    expect(controller.schedulerStatusError, isNull);

    controller.dispose();
  });

  testWidgets('Operational Readiness Open Settings button navigates',
      (tester) async {
    var openedSettings = false;
    final controller = _operationalController(
      status: _operationalStatus(mode: 'safe_mode'),
    );

    await _pumpOperationalReadiness(
      tester,
      controller,
      onOpenSettings: () => openedSettings = true,
    );

    final openSettings =
        find.byKey(const ValueKey('operational-open-settings'));
    await _showDashboardFinder(tester, openSettings);
    await tester.tap(openSettings);
    await tester.pumpAndSettle();

    expect(openedSettings, isTrue);

    controller.dispose();
  });

  testWidgets(
      'Operational Readiness Switch to Safe Mode calls preset and refreshes status',
      (tester) async {
    final api = _OperationalReadinessApiClient(
      status: _operationalStatus(mode: 'full_live_test_mode'),
    );
    final controller = _operationalController(
      api: api,
      status: _operationalStatus(mode: 'full_live_test_mode'),
    );

    await _pumpOperationalReadiness(tester, controller);

    final switchButton =
        find.byKey(const ValueKey('operational-switch-safe-mode'));
    await _showDashboardFinder(tester, switchButton);
    await tester.tap(switchButton);
    await tester.pumpAndSettle();

    expect(api.applyPresetCalls, 1);
    expect(api.lastPreset, 'safe_mode');
    expect(api.fetchSchedulerStatusCalls, 1);
    expect(controller.schedulerStatus.currentOperationMode, 'safe_mode');
    expect(controller.schedulerStatus.warningLevel, 'safe');

    controller.dispose();
  });

  testWidgets('Automation Runtime Monitor renders global safety',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor()
      ..selectedProvider = SelectedProvider.alpaca;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('automation_runtime_monitor_card'),
    );

    final card = find.byKey(const Key('automation_runtime_monitor_card'));
    expect(find.text('Automation Runtime Monitor'), findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('Global Safety')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('DRY RUN ON')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('Kill Switch OFF')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('Global Scheduler ON')),
        findsOneWidget);

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

    await _showDashboardSection(
      tester,
      const Key('automation_runtime_monitor_card'),
    );

    expect(find.text('Alpaca Paper Scheduler'), findsOneWidget);
    expect(find.textContaining('weak_final_score_gap'), findsWidgets);
    expect(find.text('KIS Live Scheduler'), findsOneWidget);
    expect(find.text('TAKE_PROFIT'), findsWidgets);
    expect(find.text('REAL ORDER SUBMITTED'), findsOneWidget);
    expect(find.text('false'), findsWidgets);
    expect(find.textContaining('market_closed'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Dashboard shows Live Sell Armed warning', (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor(
        schedulerStatus: _schedulerStatusWithRisk(_armedSellOnlyRisk),
      )
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('automation_runtime_monitor_card'),
    );

    expect(
      find.text(
        'KIS live sell automation is armed. Stop-loss sell may submit real KIS orders.',
      ),
      findsOneWidget,
    );
    expect(find.text('ARMED_SELL_ONLY'), findsNothing);
    expect(find.text('armed_sell_only'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Dashboard shows high-severity Live Buy Armed warning',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor(
        schedulerStatus: _schedulerStatusWithRisk(_dangerousBuyRisk),
      )
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('automation_runtime_monitor_card'),
    );

    expect(
      find.text(
        'KIS live buy automation is enabled. This should remain OFF unless explicitly testing.',
      ),
      findsOneWidget,
    );
    expect(
      find.textContaining('Dangerous mixed KIS automation settings detected.'),
      findsOneWidget,
    );
    expect(find.textContaining('kis_scheduler_buy_enabled'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Dashboard shows Safe Mode when risk summary is safe',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor(
        schedulerStatus:
            _schedulerStatusWithRisk(const SchedulerRiskSummary.safe()),
      )
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('automation_runtime_monitor_card'),
    );

    expect(find.text('Safe Mode / Live automation off.'), findsOneWidget);
    expect(find.text('safe'), findsWidgets);

    controller.dispose();
  });

  testWidgets(
      'Automation Runtime Monitor separates global and KIS effective scheduler state',
      (tester) async {
    const status = SchedulerStatus(
      runtimeSchedulerEnabled: true,
      us: MarketSchedulerStatus(
        enabledForScheduler: true,
        timezone: 'America/New_York',
        slots: [],
      ),
      kr: MarketSchedulerStatus(
        enabledForScheduler: false,
        timezone: 'Asia/Seoul',
        slots: [],
        realOrderSchedulerEnabled: false,
        enabledForSchedulerBlockReasons: ['kis_scheduler_disabled'],
      ),
    );
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor(schedulerStatus: status)
      ..selectedProvider = SelectedProvider.kis;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('automation_runtime_monitor_card'),
    );

    expect(find.text('Global Scheduler ON'), findsOneWidget);
    expect(
      find.textContaining('KIS Scheduler Effective: OFF'),
      findsOneWidget,
    );
    expect(
      find.textContaining('KIS Real Order Scheduler: OFF'),
      findsOneWidget,
    );
    expect(find.text('KIS SCHEDULER CONFIG'), findsOneWidget);
    expect(find.text('BLOCK REASONS'), findsOneWidget);
    expect(find.textContaining('kis_scheduler_disabled'), findsWidgets);

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

    await _showDashboardSection(
      tester,
      const Key('automation_runtime_monitor_card'),
    );
    await tester.tap(find.byKey(const ValueKey('automation-runtime-refresh')));
    await tester.pumpAndSettle();

    expect(api.fetchRecentRunsCalls, 1);
    expect(controller.automationRuntimeMonitor?.alpaca.lastResult, 'skipped');

    controller.dispose();
  });

  testWidgets('Automation Event Timeline shows latest 10 events by default',
      (tester) async {
    final events = [
      for (var i = 0; i < 12; i++)
        _event(
          id: 'timeline-$i',
          timestamp: '2026-05-28T02:${(30 - i).toString().padLeft(2, '0')}:00Z',
          provider: 'kis',
          market: 'KR',
          symbol: 'EV${i.toString().padLeft(2, '0')}',
          category: 'scheduler_run',
          result: 'hold',
        ),
    ];
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor(
        runs: const [],
        localEvents: events,
      );

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('automation_event_timeline_card'),
    );

    expect(find.text('EV00'), findsOneWidget);
    expect(find.text('EV09'), findsOneWidget);
    expect(find.text('EV10'), findsNothing);
    expect(find.text('EV11'), findsNothing);

    final showOlderButton =
        find.byKey(const ValueKey('automation-events-show-older'));
    await _showDashboardFinder(tester, showOlderButton);
    await tester.tap(showOlderButton);
    await tester.pumpAndSettle();

    expect(find.text('EV10'), findsOneWidget);
    expect(find.text('EV11'), findsOneWidget);

    controller.dispose();
  });

  testWidgets(
      'Automation Event Timeline renders KIS trigger with block reason and KST time',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor(
        runs: const [],
        localEvents: const [
          AutomationEvent(
            id: 'kis-trigger',
            timestamp: '2026-05-28T00:16:00Z',
            provider: 'kis',
            market: 'KR',
            category: 'trigger_detected',
            severity: 'warning',
            symbol: '036540',
            companyName: null,
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
            relatedRunId: '10',
            relatedSignalId: null,
            relatedOrderId: null,
            developerPayload: {},
          ),
        ],
      );

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('automation_event_timeline_card'),
    );

    final timeline =
        find.byKey(const Key('automation_event_timeline_card'));
    expect(find.descendant(of: timeline, matching: find.text('KIS LIVE')),
        findsOneWidget);
    expect(find.descendant(of: timeline, matching: find.text('036540')),
        findsOneWidget);
    expect(
        find.descendant(
            of: timeline, matching: find.text('TRIGGER DETECTED')),
        findsOneWidget);
    expect(find.descendant(of: timeline, matching: find.text('TAKE_PROFIT')),
        findsOneWidget);
    expect(find.descendant(of: timeline, matching: find.text('market_closed')),
        findsWidgets);
    expect(
        find.descendant(
            of: timeline, matching: find.textContaining('KST 09:16')),
        findsOneWidget);

    controller.dispose();
  });

  testWidgets('Automation Event Timeline renders KIS filled sell ODNO',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor(
        runs: const [],
        localEvents: const [
          AutomationEvent(
            id: 'kis-filled',
            timestamp: '2026-05-28T00:25:00Z',
            provider: 'kis',
            market: 'KR',
            category: 'order_filled',
            severity: 'success',
            symbol: '091810',
            companyName: null,
            action: 'sell',
            trigger: 'take_profit',
            result: 'FILLED',
            reason: 'FILLED',
            blockReason: null,
            orderId: '88',
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
            relatedOrderId: '88',
            developerPayload: {},
          ),
        ],
      );

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('automation_event_timeline_card'),
    );

    expect(find.text('FILLED'), findsWidgets);
    expect(find.text('ODNO'), findsOneWidget);
    expect(find.text('0021651600'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Automation Event Timeline renders Alpaca skipped block reason',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor(
        runs: const [],
        localEvents: const [
          AutomationEvent(
            id: 'alpaca-skip',
            timestamp: '2026-05-28T00:35:00Z',
            provider: 'alpaca',
            market: 'US',
            category: 'blocked',
            severity: 'info',
            symbol: 'AAPL',
            companyName: null,
            action: 'skipped',
            trigger: 'weak_signal',
            result: 'skipped',
            reason: 'weak_final_score_gap',
            blockReason: 'weak_final_score_gap',
            orderId: null,
            brokerOrderId: null,
            kisOdno: null,
            realOrderSubmitted: false,
            brokerSubmitCalled: false,
            manualSubmitCalled: false,
            source: 'watchlist',
            mode: 'watchlist_run',
            triggerSource: 'scheduler',
            relatedRunId: '11',
            relatedSignalId: null,
            relatedOrderId: null,
            developerPayload: {},
          ),
        ],
      );

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('automation_event_timeline_card'),
    );

    final timeline =
        find.byKey(const Key('automation_event_timeline_card'));
    expect(find.descendant(of: timeline, matching: find.text('ALPACA PAPER')),
        findsOneWidget);
    expect(find.descendant(of: timeline, matching: find.text('AAPL')),
        findsOneWidget);
    expect(
        find.descendant(
            of: timeline, matching: find.text('weak_final_score_gap')),
        findsWidgets);

    controller.dispose();
  });

  testWidgets('Automation Event Timeline handles partial data without crash',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor(
        runs: const [],
        localEvents: const [
          AutomationEvent(
            id: 'partial',
            timestamp: '',
            provider: 'system',
            market: '',
            category: 'portfolio_check',
            severity: 'info',
            symbol: null,
            companyName: null,
            action: 'hold',
            trigger: 'none',
            result: '',
            reason: '',
            blockReason: null,
            orderId: null,
            brokerOrderId: null,
            kisOdno: null,
            realOrderSubmitted: false,
            brokerSubmitCalled: false,
            manualSubmitCalled: false,
            source: '',
            mode: '',
            triggerSource: '',
            relatedRunId: null,
            relatedSignalId: null,
            relatedOrderId: null,
            developerPayload: {},
          ),
        ],
      );

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('automation_event_timeline_card'),
    );

    expect(find.text('Latest Automation Events'), findsOneWidget);
    expect(find.text('SYSTEM'), findsOneWidget);
    expect(find.text('PORTFOLIO CHECK'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Operation Rehearsal panel shows read-only checks',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor();

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('operation_rehearsal_panel'),
    );

    final operationPanel = find.byKey(const Key('operation_rehearsal_panel'));
    expect(find.text('SAFE CHECKS'), findsOneWidget);
    expect(find.text('Refresh Monitor'), findsOneWidget);
    expect(find.text('Check KIS Sell Gates'), findsOneWidget);
    expect(find.text('Check KIS Buy Gates'), findsOneWidget);
    expect(find.text('DRY-RUN ONLY'), findsOneWidget);
    expect(
        find.descendant(
            of: operationPanel, matching: find.text('ALPACA PAPER')),
        findsOneWidget);

    controller.dispose();
  });

  testWidgets('Check KIS Sell Gates calls status endpoint only',
      (tester) async {
    final api = FakeKisApiClient();
    final controller = DashboardController(api, autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor();

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    final button = find.byKey(const ValueKey('operation-check-kis-sell'));
    await _showDashboardFinder(tester, button);
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(api.guardedSellStatusCalls, 1);
    expect(api.guardedBuyStatusCalls, 0);
    expect(api.guardedSellRunCalls, 0);
    expect(api.guardedBuyRunCalls, 0);

    controller.dispose();
  });

  testWidgets('Check KIS Buy Gates calls status endpoint only', (tester) async {
    final api = FakeKisApiClient();
    final controller = DashboardController(api, autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor();

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    final button = find.byKey(const ValueKey('operation-check-kis-buy'));
    await _showDashboardFinder(tester, button);
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(api.guardedBuyStatusCalls, 1);
    expect(api.guardedSellStatusCalls, 0);
    expect(api.guardedSellRunCalls, 0);
    expect(api.guardedBuyRunCalls, 0);

    controller.dispose();
  });

  testWidgets(
      'Dry-run orchestration button is labeled and avoids live guarded endpoints',
      (tester) async {
    final api = FakeKisApiClient();
    final controller = DashboardController(api, autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor();

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    await _showDashboardSection(
      tester,
      const Key('operation_rehearsal_panel'),
    );
    expect(find.text('DRY-RUN ONLY'), findsOneWidget);
    final button = find.byKey(const ValueKey('operation-run-kis-dry-run'));
    await _showDashboardFinder(tester, button);
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(api.dryRunOrchestrationCalls, 1);
    expect(api.guardedSellRunCalls, 0);
    expect(api.guardedBuyRunCalls, 0);

    controller.dispose();
  });

  testWidgets('Dangerous guarded actions require confirmation', (tester) async {
    final api = FakeKisApiClient();
    final controller = DashboardController(api, autoload: false)
      ..automationRuntimeMonitor = _runtimeMonitor();

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));

    expect(
        find.byKey(const ValueKey('operation-run-guarded-sell')), findsNothing);

    final advanced = find.byKey(const ValueKey('operation-advanced-actions'));
    await _showDashboardFinder(tester, advanced);
    await tester.tap(advanced);
    await tester.pumpAndSettle();

    final sellButton = find.byKey(const ValueKey('operation-run-guarded-sell'));
    await _showDashboardFinder(tester, sellButton);
    await tester.tap(sellButton);
    await tester.pumpAndSettle();

    expect(
      find.text('This may submit a real KIS SELL order if all gates pass.'),
      findsOneWidget,
    );
    expect(api.guardedSellRunCalls, 0);

    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(api.guardedSellRunCalls, 0);
    expect(find.byKey(const ValueKey('operation-run-guarded-buy')),
        findsOneWidget);

    controller.dispose();
  });

  testWidgets(
      'Pre-Live Operations runs exit preflight without submit side effects',
      (tester) async {
    final api = FakeKisApiClient();
    final controller = DashboardController(api, autoload: false)
      ..usPortfolioSummary = _usSummary
      ..krPortfolioSummary = _krSummary
      ..kisManagedPositions = const [_krManagedPosition]
      ..selectedProvider = SelectedProvider.kis
      ..selectedPortfolioMarket = PortfolioMarket.kr
      ..settings = const OpsSettings(
        schedulerEnabled: false,
        botEnabled: false,
        dryRun: true,
        killSwitch: false,
        brokerMode: 'Paper',
        defaultGateLevel: 2,
        maxDailyTrades: 5,
        maxDailyEntries: 2,
        minEntryScore: 65,
        minScoreGap: 3,
      )
      ..schedulerStatus = SchedulerStatus.safeDefault();

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => DashboardScreen(
            controller: controller,
            onOpenManualOrder: () {},
          ),
        ),
      ),
    ));

    await _showDashboardSection(tester, const Key('pre_live_operations_card'));

    final card = find.byKey(const Key('pre_live_operations_card'));
    expect(
        find.descendant(of: card, matching: find.text('Pre-Live Operations')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('PREFLIGHT FIRST')),
        findsOneWidget);
    expect(
        find.descendant(of: card, matching: find.text('TICKET PREFILL ONLY')),
        findsOneWidget);
    expect(
        find.descendant(of: card, matching: find.text('CONFIRM_LIVE MANUAL')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('LIVE AUTO BUY OFF')),
        findsOneWidget);
    expect(
        find.descendant(
            of: card, matching: find.text('SCHEDULER REAL ORDERS OFF')),
        findsOneWidget);

    final preflightButton =
        find.byKey(const ValueKey('pre-live-run-exit-preflight'));
    await _showDashboardFinder(tester, preflightButton);
    await tester.tap(preflightButton);
    await tester.pumpAndSettle();

    expect(api.liveExitPreflightCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.kisLiveExitPreflightResult?.candidateCount, 1);
    expect(controller.orderValidationResult, isNull);
    expect(controller.kisLiveConfirmation, isFalse);

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

    await _showDashboardSection(
        tester, const Key('portfolio_snapshot_section'));

    expect(find.text('Portfolio Snapshot'), findsOneWidget);
    expect(find.byKey(const Key('portfolio_position_management_section')),
        findsOneWidget);
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

    await _showDashboardSection(
        tester, const Key('portfolio_snapshot_section'));

    final positionCard =
        find.byKey(const ValueKey('portfolio-position-card-005930'));
    await _showDashboardFinder(tester, positionCard);
    await tester.tap(positionCard);
    await tester.pumpAndSettle();

    final prepareSellButton =
        find.byKey(const ValueKey('prepare-manual-sell-005930'));
    await _showDashboardFinder(tester, prepareSellButton);

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
    expect(controller.selectedOrderMarket, PortfolioMarket.kr);
    expect(controller.orderTicketSymbol, '005930');
    expect(controller.orderTicketSide, 'sell');
    expect(controller.orderTicketQtyInput, '1');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(controller.orderValidationError, isNull);
    expect(controller.latestKisManualOrder, isNull);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => TradingScreen(controller: controller),
        ),
      ),
    ));

    expect(find.text('KIS Analyze / Validate / Submit'), findsOneWidget);
    await tester.dragUntilVisible(
      find.text('KIS Manual Buy/Sell Ticket'),
      find.byType(ListView),
      const Offset(0, -300),
    );
    await tester.pumpAndSettle();

    expect(find.text('KIS Manual Buy/Sell Ticket'), findsOneWidget);
    expect(find.text('KIS Manual SELL Ticket'), findsOneWidget);
    expect(find.text('Prepared Manual Sell'), findsOneWidget);
    expect(find.text('SELL'), findsWidgets);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('Validate Sell'), findsOneWidget);
    expect(find.text('Submit Manual Sell'), findsOneWidget);
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(controller.latestKisManualOrder, isNull);

    controller.dispose();
  });
}

Future<void> _showDashboardSection(WidgetTester tester, Key sectionKey) {
  return _showDashboardFinder(tester, find.byKey(sectionKey));
}

Future<void> _showDashboardFinder(WidgetTester tester, Finder finder) async {
  final scrollable = find.byKey(const Key('dashboard_home_scroll_view'));
  expect(scrollable, findsOneWidget);
  if (finder.evaluate().isEmpty) {
    await _expandHomeAdvancedDetails(tester);
  }
  await _scrollDashboardUntilBuilt(tester, finder, scrollable);
  expect(finder, findsOneWidget);
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
}

Future<void> _expandHomeAdvancedDetails(WidgetTester tester) async {
  if (find.byKey(const Key('operational-readiness-card'))
      .evaluate()
      .isNotEmpty) {
    return;
  }
  final scrollable = find.byKey(const Key('dashboard_home_scroll_view'));
  final toggle = find.byKey(const ValueKey('home-advanced-details-toggle'));
  await _scrollDashboardUntilBuilt(tester, toggle, scrollable);
  if (toggle.evaluate().isEmpty) return;
  await tester.ensureVisible(toggle);
  await tester.pumpAndSettle();
  await tester.tap(toggle);
  await tester.pumpAndSettle();
}

Future<void> _scrollDashboardUntilBuilt(
  WidgetTester tester,
  Finder finder,
  Finder scrollable,
) async {
  for (var i = 0; i < 30 && finder.evaluate().isEmpty; i++) {
    await tester.drag(scrollable, const Offset(0, -350));
    await tester.pumpAndSettle();
  }
}

DashboardController _operationalController({
  _OperationalReadinessApiClient? api,
  required SchedulerStatus status,
}) {
  final fake = api ?? _OperationalReadinessApiClient(status: status);
  return DashboardController(fake, autoload: false)
    ..settings = fake.currentSettings
    ..schedulerStatus = status
    ..schedulerStatusLoaded = true
    ..selectedProvider = SelectedProvider.kis;
}

Future<void> _pumpOperationalReadiness(
  WidgetTester tester,
  DashboardController controller, {
  VoidCallback? onOpenSettings,
}) async {
  await tester.pumpWidget(MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: DashboardScreen(
        controller: controller,
        onOpenSettings: onOpenSettings,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await _expandHomeAdvancedDetails(tester);
}

class _OperationalReadinessApiClient extends ApiClient {
  _OperationalReadinessApiClient({required SchedulerStatus status})
      : currentStatus = status,
        currentSettings = _operationalSettingsForMode(
          status.currentOperationMode,
        );

  SchedulerStatus currentStatus;
  OpsSettings currentSettings;
  int fetchSchedulerStatusCalls = 0;
  int applyPresetCalls = 0;
  String? lastPreset;

  @override
  Future<OpsSettings> getOpsSettings() async => currentSettings;

  @override
  Future<SchedulerStatus> fetchSchedulerStatus() async {
    fetchSchedulerStatusCalls += 1;
    return currentStatus;
  }

  @override
  Future<Map<String, dynamic>> applyOpsSettingsPreset({
    required String preset,
    bool confirmDangerous = false,
  }) async {
    applyPresetCalls += 1;
    lastPreset = preset;
    currentSettings = _operationalSettingsForMode(preset);
    currentStatus = _operationalStatus(mode: preset);
    return {
      'preset': preset,
      'applied': true,
      'requires_confirmation': false,
    };
  }

  @override
  Future<KisSchedulerGuardedSellResult>
      fetchKisSchedulerGuardedSellStatus() async {
    return KisSchedulerGuardedSellResult.fromJson({
      'result': 'blocked',
      'reason': 'test',
    });
  }

  @override
  Future<KisSchedulerGuardedBuyResult>
      fetchKisSchedulerGuardedBuyStatus() async {
    return KisSchedulerGuardedBuyResult.fromJson({
      'result': 'blocked',
      'reason': 'test',
    });
  }

  @override
  Future<StrategyProfileList> fetchStrategyProfiles() async =>
      _safeStrategyProfileList();
}

StrategyProfileList _safeStrategyProfileList() {
  const profile = {
    'id': 1,
    'profile_name': 'safe',
    'display_name': '안정형',
    'description': 'Safe test profile',
    'monthly_target_return_pct': 0.015,
    'monthly_target_min_pct': 0.01,
    'monthly_target_max_pct': 0.02,
    'monthly_max_loss_pct': -0.02,
    'daily_max_loss_pct': -0.005,
    'max_order_notional_pct': 0.02,
    'max_order_notional_krw': 30000,
    'max_trades_per_day': 1,
    'max_positions': 2,
    'buy_score_threshold': 75,
    'sell_score_threshold': 65,
    'stop_loss_pct': -0.012,
    'take_profit_pct': 0.02,
    'max_holding_days': 5,
    'stop_after_monthly_target': true,
    'reduce_size_after_loss': true,
    'consecutive_loss_reduce_threshold': 1,
    'is_active': true,
    'is_builtin': true,
  };
  return StrategyProfileList.fromJson({
    'profiles': [profile],
    'active_profile': profile,
  });
}

OpsSettings _operationalSettingsForMode(String mode) {
  final sellOnly = mode == 'kis_sell_only_automation';
  final fullLive = mode == 'full_live_test_mode';
  final dryRunSimulation = mode == 'dry_run_simulation';
  return OpsSettings(
    schedulerEnabled: sellOnly || fullLive || dryRunSimulation,
    botEnabled: false,
    dryRun: !(sellOnly || fullLive),
    killSwitch: false,
    brokerMode: 'Paper',
    defaultGateLevel: 2,
    maxDailyTrades: 5,
    maxDailyEntries: 2,
    minEntryScore: 65,
    minScoreGap: 3,
    currentOperationMode: mode,
    maxLiveOrdersPerDay: 2,
    kisSchedulerEnabled: sellOnly || fullLive || dryRunSimulation,
    kisSchedulerDryRun: dryRunSimulation || mode == 'safe_mode',
    kisSchedulerLiveEnabled: sellOnly || fullLive,
    kisSchedulerAllowRealOrders: sellOnly || fullLive,
    kisSchedulerConfiguredAllowRealOrders: sellOnly || fullLive,
    kisSchedulerSellEnabled: sellOnly || fullLive,
    kisSchedulerBuyEnabled: fullLive,
    kisSchedulerAllowLimitedAutoSell: sellOnly || fullLive,
    kisSchedulerAllowLimitedAutoBuy: fullLive,
    kisLiveAutoSellEnabled: sellOnly || fullLive,
    kisLiveAutoBuyEnabled: fullLive,
    kisLimitedAutoStopLossEnabled: sellOnly || fullLive,
    kisLimitedAutoSellStopLossEnabled: sellOnly || fullLive,
    kisLimitedAutoTakeProfitEnabled: sellOnly || fullLive,
    kisLimitedAutoSellTakeProfitEnabled: sellOnly || fullLive,
    kisLimitedAutoBuyEnabled: fullLive,
    krNoNewEntryAfter: '14:40',
    noNewEntryAfter: '14:40',
    kisLimitedAutoBuyNoNewEntryAfter: '14:40',
  );
}

SchedulerStatus _operationalStatus({
  required String mode,
  int? dailyRemaining,
  bool killSwitch = false,
  String usNoNewEntryAfter = '15:45',
  String krNoNewEntryAfter = '14:40',
}) {
  final sellOnly = mode == 'kis_sell_only_automation';
  final fullLive = mode == 'full_live_test_mode';
  final dryRunSimulation = mode == 'dry_run_simulation';
  final risk = SchedulerRiskSummary(
    liveSellArmed: sellOnly || fullLive,
    liveBuyArmed: fullLive,
    sellOnlyMode: sellOnly,
    dailyLiveOrderLimit: 2,
    dailyLiveOrderRemaining:
        sellOnly || fullLive ? (dailyRemaining ?? 1) : null,
    maxNotionalPct: 0.03,
    dryRun: !(sellOnly || fullLive),
    killSwitch: killSwitch,
    safeModeActive: mode == 'safe_mode',
    riskyFlags: fullLive ? const ['kis_scheduler_buy_enabled'] : const [],
    blockingFlags: const [],
    warningLevel: fullLive
        ? 'dangerous_mixed'
        : sellOnly
            ? 'armed_sell_only'
            : 'safe',
    sellGateEnabled: sellOnly || fullLive,
    buyGateEnabled: fullLive,
  );
  final schedulerEnabled = sellOnly || fullLive || dryRunSimulation;
  return SchedulerStatus(
    runtimeSchedulerEnabled: schedulerEnabled,
    global: SchedulerGlobalStatus(
      schedulerEnabled: schedulerEnabled,
      dryRun: !(sellOnly || fullLive),
      killSwitch: killSwitch,
      safeModeActive: mode == 'safe_mode',
    ),
    currentOperationMode: mode,
    displayModeLabel: operationModeLabel(mode),
    displayWarningLevel: risk.warningLevel,
    userFriendlySummary: _operationalSummary(mode),
    riskSummary: risk,
    liveOrderPossible: sellOnly || fullLive,
    liveBuyPossible: fullLive,
    liveSellPossible: sellOnly || fullLive,
    dailyLiveOrderRemaining: risk.dailyLiveOrderRemaining,
    warningMessage: _operationalWarning(mode, risk.dailyLiveOrderRemaining),
    us: MarketSchedulerStatus(
      enabledForScheduler: schedulerEnabled,
      market: 'US',
      broker: 'alpaca',
      timezone: 'America/New_York',
      slots: const ['open_phase 09:30'],
      nextSlotName: 'open_phase',
      nextSlotTimeLocal: '2026-06-11T09:30',
      noNewEntryAfter: usNoNewEntryAfter,
    ),
    kr: MarketSchedulerStatus(
      enabledForScheduler: schedulerEnabled,
      market: 'KR',
      broker: 'kis',
      timezone: 'Asia/Seoul',
      slots: const ['midday 11:30'],
      nextSlotName: 'midday',
      nextSlotTimeLocal: '2026-06-12T11:30',
      noNewEntryAfter: krNoNewEntryAfter,
      realOrderSchedulerEnabled: sellOnly || fullLive,
      liveSchedulerReady: sellOnly || fullLive,
      liveBuyArmed: fullLive,
      liveSellArmed: sellOnly || fullLive,
      riskSummary: risk,
    ),
  );
}

String _operationalSummary(String mode) {
  switch (mode) {
    case 'dry_run_simulation':
      return 'Dry-run simulation is enabled. Scheduler checks can run without real orders.';
    case 'kis_sell_only_automation':
      return 'KIS sell-only live automation is armed. Auto-buy is disabled.';
    case 'full_live_test_mode':
      return 'Full live test mode is armed. Live buy and live sell automation are enabled.';
    default:
      return 'Safe mode is active. Scheduler live buy and sell automation are disabled.';
  }
}

String _operationalWarning(String mode, int? dailyRemaining) {
  switch (mode) {
    case 'kis_sell_only_automation':
      return 'LIVE SELL ARMED. Auto-buy is disabled. Daily live orders remaining: ${dailyRemaining ?? 1}.';
    case 'full_live_test_mode':
      return 'LIVE BUY ARMED and LIVE SELL ARMED may be possible. Full live test mode is dangerous.';
    default:
      return 'No scheduler live buy or sell automation is armed.';
  }
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

Map<String, dynamic> _liveExitPreflightJson() {
  return {
    'status': 'ok',
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_live_exit_preflight',
    'execution_mode': 'manual_confirm_only',
    'action': 'sell',
    'symbol': '005930',
    'qty': 1,
    'candidate_count': 1,
    'candidates': [
      {
        'symbol': '005930',
        'side': 'sell',
        'quantity_available': 1,
        'suggested_quantity': 1,
        'current_price': 600000,
        'estimated_notional': 600000,
        'cost_basis': 500000,
        'current_value': 600000,
        'unrealized_pl': 100000,
        'unrealized_pl_pct': 0.2,
        'trigger': 'take_profit',
        'trigger_source': 'portfolio_snapshot',
        'severity': 'review',
        'action_hint': 'manual_confirm_sell',
        'reason': 'take_profit_triggered',
        'submit_ready': false,
        'manual_confirm_required': true,
        'real_order_submit_allowed': false,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      }
    ],
    'reason': 'take_profit_triggered',
    'would_submit_if_enabled': false,
    'live_order_submitted': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'manual_confirm_required': true,
    'real_order_submit_allowed': false,
    'auto_buy_enabled': false,
    'auto_sell_enabled': false,
    'blocked_by': ['preflight_only_no_broker_submit'],
  };
}

AutomationRuntimeMonitor _runtimeMonitor({
  List<AutomationEvent> localEvents = const [],
  List<OrderLogItem> orders = const [],
  List<TradingLogItem>? runs,
  OpsSettings settings = const OpsSettings(
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
  SchedulerStatus schedulerStatus = const SchedulerStatus(
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
}) {
  final sourceRuns = runs ??
      const [
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
      ];
  return AutomationRuntimeMonitor.fromSources(
    settings: settings,
    schedulerStatus: schedulerStatus,
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
    runs: sourceRuns,
    orders: orders,
    localEvents: localEvents,
  );
}

SchedulerStatus _schedulerStatusWithRisk(SchedulerRiskSummary risk) {
  return SchedulerStatus(
    runtimeSchedulerEnabled: true,
    us: const MarketSchedulerStatus(
      enabledForScheduler: true,
      timezone: 'America/New_York',
      slots: [],
    ),
    kr: MarketSchedulerStatus(
      enabledForScheduler: risk.liveSellArmed || risk.liveBuyArmed,
      timezone: 'Asia/Seoul',
      slots: const [],
      previewOnly: true,
      realOrdersAllowed: risk.liveSellArmed || risk.liveBuyArmed,
      realOrderSchedulerEnabled: risk.liveSellArmed || risk.liveBuyArmed,
      liveSchedulerReady: risk.liveSellArmed || risk.liveBuyArmed,
      riskSummary: risk,
    ),
  );
}

const _armedSellOnlyRisk = SchedulerRiskSummary(
  liveSellArmed: true,
  liveBuyArmed: false,
  sellOnlyMode: true,
  dailyLiveOrderLimit: 1,
  dailyLiveOrderRemaining: 1,
  maxNotionalPct: 0.03,
  dryRun: false,
  killSwitch: false,
  safeModeActive: false,
  riskyFlags: [],
  blockingFlags: [],
  warningLevel: 'armed_sell_only',
  sellGateEnabled: true,
  buyGateEnabled: false,
);

const _dangerousBuyRisk = SchedulerRiskSummary(
  liveSellArmed: true,
  liveBuyArmed: true,
  sellOnlyMode: false,
  dailyLiveOrderLimit: 1,
  dailyLiveOrderRemaining: 1,
  maxNotionalPct: 0.03,
  dryRun: false,
  killSwitch: false,
  safeModeActive: false,
  riskyFlags: ['kis_scheduler_buy_enabled'],
  blockingFlags: [],
  warningLevel: 'dangerous_mixed',
  sellGateEnabled: true,
  buyGateEnabled: true,
);

AutomationEvent _event({
  required String id,
  required String timestamp,
  required String provider,
  required String market,
  required String? symbol,
  required String category,
  String severity = 'info',
  String action = 'hold',
  String trigger = 'none',
  String result = '',
  String reason = '',
  String? blockReason,
}) {
  return AutomationEvent(
    id: id,
    timestamp: timestamp,
    provider: provider,
    market: market,
    category: category,
    severity: severity,
    symbol: symbol,
    companyName: null,
    action: action,
    trigger: trigger,
    result: result,
    reason: reason,
    blockReason: blockReason,
    orderId: null,
    brokerOrderId: null,
    kisOdno: null,
    realOrderSubmitted: false,
    brokerSubmitCalled: false,
    manualSubmitCalled: false,
    source: 'test',
    mode: 'test',
    triggerSource: 'test',
    relatedRunId: null,
    relatedSignalId: null,
    relatedOrderId: null,
    developerPayload: const {},
  );
}
