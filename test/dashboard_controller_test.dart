import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
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
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient({this.latest, this.throwLatest = false});

  final WatchlistRunResult? latest;
  final bool throwLatest;
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
