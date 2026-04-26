import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../models/ops_settings.dart';
import '../../models/trading_run.dart';
import '../../models/watchlist_run_result.dart';

class DashboardController extends ChangeNotifier {
  DashboardController(this.apiClient) {
    load();
  }

  final ApiClient apiClient;

  OpsSettings settings = const OpsSettings(
    schedulerEnabled: false,
    botEnabled: false,
    dryRun: true,
    killSwitch: false,
    brokerMode: 'Paper',
    maxDailyTrades: 5,
    maxDailyEntries: 2,
    minEntryScore: 65,
    minScoreGap: 3,
  );

  WatchlistRunResult runResult = const WatchlistRunResult(
    configuredSymbolCount: 50,
    analyzedSymbolCount: 50,
    quantCandidatesCount: 5,
    researchedCandidatesCount: 5,
    finalBestCandidate: 'WMT',
    secondFinalCandidate: 'CSCO',
    tiedFinalCandidates: ['WMT', 'CSCO', 'APP'],
    nearTiedCandidates: ['WMT', 'CSCO', 'APP'],
    tieBreakerApplied: true,
    finalCandidateSelectionReason: 'Tie-breaker prioritized stability and volume momentum among near-tied final candidates.',
    bestScore: 68,
    finalScoreGap: 0,
    minEntryScore: 65,
    minScoreGap: 3,
    shouldTrade: false,
    triggeredSymbol: null,
    triggerBlockReason: 'weak_final_score_gap',
    action: 'hold',
    orderId: null,
    topQuantCandidates: [],
    researchedCandidates: [],
    finalRankedCandidates: [],
    result: 'skipped',
    reason: 'weak_final_score_gap',
    triggerSource: 'manual',
  );

  List<TradingRun> recentRuns = const [];
  String? error;
  bool loading = false;

  Future<void> load() async {
    loading = true;
    notifyListeners();
    try {
      settings = await apiClient.getOpsSettings();
      runResult = apiClient.getMockRunResult();
      recentRuns = await apiClient.getRecentTradingRuns();
      error = null;
    } catch (e) {
      error = e.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> runOnce() async {
    try {
      await apiClient.runWatchlistOnce();
    } catch (e) {
      error = 'Run request failed: $e';
    }
    notifyListeners();
  }

  Future<void> toggleScheduler(bool v) async {
    settings = OpsSettings(
      schedulerEnabled: v,
      botEnabled: settings.botEnabled,
      dryRun: settings.dryRun,
      killSwitch: settings.killSwitch,
      brokerMode: settings.brokerMode,
      maxDailyTrades: settings.maxDailyTrades,
      maxDailyEntries: settings.maxDailyEntries,
      minEntryScore: settings.minEntryScore,
      minScoreGap: settings.minScoreGap,
    );
    notifyListeners();
    try {
      v ? await apiClient.schedulerOn() : await apiClient.schedulerOff();
    } catch (e) {
      error = 'Scheduler call failed: $e';
    }
    notifyListeners();
  }

  Future<void> toggleBot(bool v) async {
    settings = OpsSettings(
      schedulerEnabled: settings.schedulerEnabled,
      botEnabled: v,
      dryRun: settings.dryRun,
      killSwitch: settings.killSwitch,
      brokerMode: settings.brokerMode,
      maxDailyTrades: settings.maxDailyTrades,
      maxDailyEntries: settings.maxDailyEntries,
      minEntryScore: settings.minEntryScore,
      minScoreGap: settings.minScoreGap,
    );
    notifyListeners();
    try {
      v ? await apiClient.botOn() : await apiClient.botOff();
    } catch (e) {
      error = 'Bot call failed: $e';
    }
    notifyListeners();
  }

  Future<void> toggleKillSwitch(bool v) async {
    settings = OpsSettings(
      schedulerEnabled: settings.schedulerEnabled,
      botEnabled: settings.botEnabled,
      dryRun: settings.dryRun,
      killSwitch: v,
      brokerMode: settings.brokerMode,
      maxDailyTrades: settings.maxDailyTrades,
      maxDailyEntries: settings.maxDailyEntries,
      minEntryScore: settings.minEntryScore,
      minScoreGap: settings.minScoreGap,
    );
    notifyListeners();
    try {
      v ? await apiClient.killSwitchOn() : await apiClient.killSwitchOff();
    } catch (e) {
      error = 'Kill switch call failed: $e';
    }
    notifyListeners();
  }

  void setDryRun(bool v) {
    settings = OpsSettings(
      schedulerEnabled: settings.schedulerEnabled,
      botEnabled: settings.botEnabled,
      dryRun: v,
      killSwitch: settings.killSwitch,
      brokerMode: settings.brokerMode,
      maxDailyTrades: settings.maxDailyTrades,
      maxDailyEntries: settings.maxDailyEntries,
      minEntryScore: settings.minEntryScore,
      minScoreGap: settings.minScoreGap,
    );
    notifyListeners();
  }
}
