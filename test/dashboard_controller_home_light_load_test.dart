import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/agent_chat_live_order_readiness.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/managed_position.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';
import 'package:auto_invest_dashboard/models/scheduler_status.dart';
import 'package:auto_invest_dashboard/models/strategy_dry_run_auto_buy.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_buy.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_exit.dart';
import 'package:auto_invest_dashboard/models/strategy_performance.dart';
import 'package:auto_invest_dashboard/models/strategy_profile.dart';
import 'package:auto_invest_dashboard/models/strategy_risk.dart';
import 'package:auto_invest_dashboard/models/watchlist_run_result.dart';

void main() {
  test('DashboardController.load keeps Home load light', () async {
    final api = _HomeLightApiClient();
    final controller = DashboardController(api, autoload: false);

    await controller.load().timeout(const Duration(seconds: 1));

    expect(api.recentRunsLimit, 3);
    expect(api.recentOrdersLimit, 3);
    expect(api.fetchRecentSignalsCalls, 0);
    expect(controller.recentRuns, hasLength(1));
    expect(controller.automationRecentOrders, hasLength(1));

    expect(api.strategyProfilesCalls, 0);
    expect(api.strategyDailyPerformanceCalls, 0);
    expect(api.strategyMonthlyPerformanceCalls, 0);
    expect(api.strategyTradePerformanceCalls, 0);
    expect(api.strategyRiskStateCalls, 0);
    expect(api.strategyDryRunRecentCalls, 0);
    expect(api.strategyLiveAutoBuyReadinessCalls, 0);
    expect(api.strategyLiveAutoBuyRecentCalls, 0);
    expect(api.strategyLiveAutoExitReadinessCalls, 0);
    expect(api.strategyLiveAutoExitRecentCalls, 0);

    controller.dispose();
  });
}

class _HomeLightApiClient extends ApiClient {
  int? recentRunsLimit;
  int? recentOrdersLimit;
  int fetchRecentSignalsCalls = 0;
  int strategyProfilesCalls = 0;
  int strategyDailyPerformanceCalls = 0;
  int strategyMonthlyPerformanceCalls = 0;
  int strategyTradePerformanceCalls = 0;
  int strategyRiskStateCalls = 0;
  int strategyDryRunRecentCalls = 0;
  int strategyLiveAutoBuyReadinessCalls = 0;
  int strategyLiveAutoBuyRecentCalls = 0;
  int strategyLiveAutoExitReadinessCalls = 0;
  int strategyLiveAutoExitRecentCalls = 0;

  final _strategyProfiles = Completer<StrategyProfileList>();
  final _dailyPerformance = Completer<StrategyDailyPerformance>();
  final _monthlyPerformance = Completer<StrategyMonthlyPerformance>();
  final _tradePerformance = Completer<StrategyTradePerformanceList>();
  final _riskState = Completer<StrategyRiskState>();
  final _dryRunRecent = Completer<StrategyDryRunAutoBuyRecent>();
  final _liveBuyReadiness = Completer<StrategyLiveAutoBuyReadiness>();
  final _liveBuyRecent = Completer<StrategyLiveAutoBuyRecent>();
  final _liveExitReadiness = Completer<StrategyLiveAutoExitReadiness>();
  final _liveExitRecent = Completer<StrategyLiveAutoExitRecent>();

  @override
  Future<OpsSettings> getOpsSettings() async => const OpsSettings(
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
      );

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async =>
      KisManualOrderSafetyStatus.safeDefault;

  @override
  Future<SchedulerStatus> fetchSchedulerStatus() async =>
      SchedulerStatus.safeDefault();

  @override
  Future<AgentChatLiveOrderReadiness>
      fetchAgentChatLiveOrderReadiness() async =>
          AgentChatLiveOrderReadiness.fromJson({
            'status': 'blocked',
            'ready': false,
            'summary': 'blocked',
            'checks': const [],
          });

  @override
  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async =>
      KisSchedulerSimulationStatus.safeDefault();

  @override
  Future<MarketWatchlist> fetchMarketWatchlist(String market) async =>
      MarketWatchlist.empty(market);

  @override
  Future<PortfolioSummary> fetchUsPortfolioSummary() async =>
      PortfolioSummary.empty(currency: 'USD');

  @override
  Future<PortfolioSummary> fetchKrPortfolioSummary() async =>
      PortfolioSummary.empty(currency: 'KRW');

  @override
  Future<List<ManagedPosition>> fetchKisManagedPositions() async => const [];

  @override
  Future<WatchlistRunResult?> fetchLatestWatchlistRunResult() async => null;

  @override
  Future<List<TradingLogItem>> fetchRecentRuns({int limit = 20}) async {
    recentRunsLimit = limit;
    return [
      TradingLogItem(
        id: 1,
        runKey: 'run-1',
        symbol: 'AAPL',
        triggerSource: 'scheduler',
        mode: 'watchlist',
        action: 'hold',
        result: 'skipped',
        reason: 'weak_signal',
        relatedOrderId: null,
        createdAt: '2026-06-26T01:00:00Z',
        gateLevel: 2,
      ),
    ];
  }

  @override
  Future<List<OrderLogItem>> fetchRecentOrders({int limit = 20}) async {
    recentOrdersLimit = limit;
    return [
      OrderLogItem(
        id: 1,
        symbol: 'AAPL',
        side: 'buy',
        qty: 1,
        notional: 100,
        brokerOrderId: 'broker-1',
        brokerStatus: 'filled',
        internalStatus: 'FILLED',
        createdAt: '2026-06-26T01:00:00Z',
        updatedAt: '2026-06-26T01:00:00Z',
      ),
    ];
  }

  @override
  Future<List<SignalLogItem>> fetchRecentSignals({int limit = 20}) async {
    fetchRecentSignalsCalls += 1;
    return const [];
  }

  @override
  Future<StrategyProfileList> fetchStrategyProfiles() {
    strategyProfilesCalls += 1;
    return _strategyProfiles.future;
  }

  @override
  Future<StrategyDailyPerformance> fetchStrategyDailyPerformance({
    String provider = 'kis',
    String market = 'KR',
    String? date,
  }) {
    strategyDailyPerformanceCalls += 1;
    return _dailyPerformance.future;
  }

  @override
  Future<StrategyMonthlyPerformance> fetchStrategyMonthlyPerformance({
    String provider = 'kis',
    String market = 'KR',
    String? month,
  }) {
    strategyMonthlyPerformanceCalls += 1;
    return _monthlyPerformance.future;
  }

  @override
  Future<StrategyTradePerformanceList> fetchStrategyTradePerformance({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    int limit = 20,
  }) {
    strategyTradePerformanceCalls += 1;
    return _tradePerformance.future;
  }

  @override
  Future<StrategyRiskState> fetchStrategyRiskState({
    String provider = 'kis',
    String market = 'KR',
  }) {
    strategyRiskStateCalls += 1;
    return _riskState.future;
  }

  @override
  Future<StrategyDryRunAutoBuyRecent> fetchStrategyDryRunAutoBuyRecent({
    String provider = 'kis',
    String market = 'KR',
    String? profileName,
    String? symbol,
    int limit = 20,
  }) {
    strategyDryRunRecentCalls += 1;
    return _dryRunRecent.future;
  }

  @override
  Future<StrategyLiveAutoBuyReadiness> fetchStrategyLiveAutoBuyReadiness({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    int? sourceDryRunId,
  }) {
    strategyLiveAutoBuyReadinessCalls += 1;
    return _liveBuyReadiness.future;
  }

  @override
  Future<StrategyLiveAutoBuyRecent> fetchStrategyLiveAutoBuyRecent({
    String provider = 'kis',
    String market = 'KR',
    int limit = 20,
  }) {
    strategyLiveAutoBuyRecentCalls += 1;
    return _liveBuyRecent.future;
  }

  @override
  Future<StrategyLiveAutoExitReadiness> fetchStrategyLiveAutoExitReadiness({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
  }) {
    strategyLiveAutoExitReadinessCalls += 1;
    return _liveExitReadiness.future;
  }

  @override
  Future<StrategyLiveAutoExitRecent> fetchStrategyLiveAutoExitRecent({
    String provider = 'kis',
    String market = 'KR',
    int limit = 20,
  }) {
    strategyLiveAutoExitRecentCalls += 1;
    return _liveExitRecent.future;
  }
}
