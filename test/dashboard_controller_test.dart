import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';
import 'package:auto_invest_dashboard/models/watchlist_run_result.dart';

void main() {
  test('load uses latest backend watchlist result without mock overwrite',
      () async {
    final api = _FakeApiClient(latest: _resultFor('NVDA'));
    final controller = DashboardController(api, autoload: false);

    await controller.load();

    expect(controller.hasLatestRunResult, isTrue);
    expect(controller.showingOfflineFallback, isFalse);
    expect(controller.runResult.finalBestCandidate, 'NVDA');
    expect(api.mockCalls, 0);

    controller.dispose();
  });

  test('load keeps neutral state when backend has no watchlist run', () async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false);

    await controller.load();

    expect(controller.hasLatestRunResult, isFalse);
    expect(controller.showingOfflineFallback, isFalse);
    expect(controller.runResult.finalBestCandidate, isEmpty);
    expect(api.mockCalls, 0);

    controller.dispose();
  });

  test('load uses labeled mock fallback only when latest fetch fails',
      () async {
    final api = _FakeApiClient(throwLatest: true);
    final controller = DashboardController(api, autoload: false);

    await controller.load();

    expect(controller.hasLatestRunResult, isFalse);
    expect(controller.showingOfflineFallback, isTrue);
    expect(controller.runResult.finalBestCandidate, 'MOCK');
    expect(api.mockCalls, greaterThanOrEqualTo(1));

    controller.dispose();
  });

  test('portfolio market defaults to US and keeps summaries separate', () async {
    final api = _FakeApiClient(
      usPortfolio: _portfolio('USD', marketValue: 1200),
      krPortfolio: _portfolio('KRW', marketValue: 2500000),
    );
    final controller = DashboardController(api, autoload: false);

    await controller.load();

    expect(controller.selectedPortfolioMarket, PortfolioMarket.us);
    expect(controller.selectedPortfolioSummary.currency, 'USD');
    expect(controller.selectedPortfolioSummary.totalMarketValue, 1200);

    controller.selectPortfolioMarket(PortfolioMarket.kr);

    expect(controller.selectedPortfolioSummary.currency, 'KRW');
    expect(controller.selectedPortfolioSummary.totalMarketValue, 2500000);
    expect(controller.usPortfolioSummary.totalMarketValue, 1200);
    expect(controller.krPortfolioSummary.totalMarketValue, 2500000);

    controller.dispose();
  });

  test('KR portfolio unavailable does not crash dashboard state', () async {
    final api = _FakeApiClient(throwKrPortfolio: true);
    final controller = DashboardController(api, autoload: false);

    await controller.load();
    controller.selectPortfolioMarket(PortfolioMarket.kr);

    expect(controller.krPortfolioUnavailable, isTrue);
    expect(controller.selectedPortfolioUnavailable, isTrue);
    expect(controller.selectedPortfolioSummary.currency, 'KRW');
    expect(controller.selectedPortfolioSummary.positions, isEmpty);

    controller.dispose();
  });
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient({
    this.latest,
    this.throwLatest = false,
    this.usPortfolio,
    this.krPortfolio,
    this.throwKrPortfolio = false,
  });

  final WatchlistRunResult? latest;
  final bool throwLatest;
  final PortfolioSummary? usPortfolio;
  final PortfolioSummary? krPortfolio;
  final bool throwKrPortfolio;
  int mockCalls = 0;

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
  Future<PortfolioSummary> fetchPortfolioSummary() async =>
      usPortfolio ?? PortfolioSummary.empty();

  @override
  Future<PortfolioSummary> fetchKrPortfolioSummary() async {
    if (throwKrPortfolio) {
      throw const ApiRequestException('KIS unavailable');
    }
    return krPortfolio ?? PortfolioSummary.empty(currency: 'KRW');
  }

  @override
  Future<WatchlistRunResult?> fetchLatestWatchlistRunResult() async {
    if (throwLatest) {
      throw const ApiRequestException('offline');
    }
    return latest;
  }

  @override
  Future<List<TradingRun>> getRecentTradingRuns() async => const [];

  @override
  WatchlistRunResult getMockRunResult() {
    mockCalls += 1;
    return _resultFor('MOCK');
  }
}

PortfolioSummary _portfolio(String currency, {required double marketValue}) {
  return PortfolioSummary(
    currency: currency,
    positionsCount: 0,
    pendingOrdersCount: 0,
    totalCostBasis: 0,
    totalMarketValue: marketValue,
    totalUnrealizedPl: 0,
    totalUnrealizedPlpc: 0,
    positions: const [],
    pendingOrders: const [],
  );
}

WatchlistRunResult _resultFor(String symbol) {
  return WatchlistRunResult(
    configuredSymbolCount: 50,
    analyzedSymbolCount: 50,
    quantCandidatesCount: 1,
    researchedCandidatesCount: 1,
    finalBestCandidate: symbol,
    secondFinalCandidate: 'MSFT',
    tiedFinalCandidates: const [],
    nearTiedCandidates: const [],
    tieBreakerApplied: false,
    finalCandidateSelectionReason: '$symbol selected',
    bestScore: 72,
    finalScoreGap: 8,
    minEntryScore: 65,
    minScoreGap: 3,
    shouldTrade: false,
    triggeredSymbol: null,
    triggerBlockReason: 'weak_final_score_gap',
    finalEntryReady: false,
    finalActionHint: 'watch',
    action: 'hold',
    orderId: null,
    topQuantCandidates: const [],
    researchedCandidates: const [],
    finalRankedCandidates: const [],
    result: 'skipped',
    reason: 'weak_final_score_gap',
    triggerSource: 'manual',
  );
}
