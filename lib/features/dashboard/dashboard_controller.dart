import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../models/ops_settings.dart';
import '../../models/trading_run.dart';
import '../../models/watchlist_run_result.dart';

enum BackendConnectionStatus { connected, offline, error }

enum SettingKey { scheduler, bot, dryRun, killSwitch }

class DashboardController extends ChangeNotifier {
  DashboardController(this.apiClient) {
    loadInitial();
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
  final Set<SettingKey> pendingSettings = <SettingKey>{};
  final Set<SettingKey> unavailableControls = <SettingKey>{};

  bool loading = false;
  bool runInProgress = false;
  String? bannerWarning;
  String? lastActionMessage;
  DateTime? lastActionAt;
  DateTime? lastSettingsSyncAt;
  BackendConnectionStatus connectionStatus = BackendConnectionStatus.offline;

  bool isPending(SettingKey key) => pendingSettings.contains(key);
  bool isControlAvailable(SettingKey key) => !unavailableControls.contains(key);

  Future<void> loadInitial() async {
    loading = true;
    notifyListeners();
    try {
      await refreshSettings();
      try {
        recentRuns = await apiClient.getRecentTradingRuns();
      } catch (_) {
        recentRuns = const [];
      }
      runResult = apiClient.getMockRunResult();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> refreshSettings() async {
    try {
      settings = await apiClient.getOpsSettings();
      connectionStatus = BackendConnectionStatus.connected;
      bannerWarning = null;
      lastSettingsSyncAt = DateTime.now();
    } on ApiException catch (e) {
      connectionStatus = e.message.contains('unreachable') ? BackendConnectionStatus.offline : BackendConnectionStatus.error;
      bannerWarning = e.message;
    } catch (e) {
      connectionStatus = BackendConnectionStatus.error;
      bannerWarning = e.toString();
    }
    notifyListeners();
  }

  Future<String> runWatchlistOnce() async {
    runInProgress = true;
    notifyListeners();
    try {
      final result = await apiClient.runWatchlistOnce();
      runResult = result;
      lastActionAt = DateTime.now();
      lastActionMessage = 'Watchlist run completed: ${result.action} / ${result.result}';
      connectionStatus = BackendConnectionStatus.connected;
      return lastActionMessage!;
    } on ApiException catch (e) {
      connectionStatus = e.message.contains('unreachable') ? BackendConnectionStatus.offline : BackendConnectionStatus.error;
      final msg = 'Failed watchlist run: ${e.message}';
      bannerWarning = msg;
      return msg;
    } finally {
      runInProgress = false;
      notifyListeners();
    }
  }

  Future<String> toggleScheduler(bool enable) => _toggleSetting(
        key: SettingKey.scheduler,
        updater: () => enable ? apiClient.schedulerOn() : apiClient.schedulerOff(),
        applyOptimistic: () => settings = settings.copyWith(schedulerEnabled: enable),
        success: enable ? 'Scheduler enabled' : 'Scheduler disabled',
      );

  Future<String> toggleBot(bool enable) => _toggleSetting(
        key: SettingKey.bot,
        updater: () => enable ? apiClient.botOn() : apiClient.botOff(),
        applyOptimistic: () => settings = settings.copyWith(botEnabled: enable),
        success: enable ? 'Bot enabled' : 'Bot disabled',
      );

  Future<String> toggleDryRun(bool enable) => _toggleSetting(
        key: SettingKey.dryRun,
        updater: () => enable ? apiClient.dryRunOn() : apiClient.dryRunOff(),
        applyOptimistic: () => settings = settings.copyWith(dryRun: enable),
        success: enable ? 'Dry Run enabled' : 'Dry Run disabled',
      );

  Future<String> toggleKillSwitch(bool enable) => _toggleSetting(
        key: SettingKey.killSwitch,
        updater: () => enable ? apiClient.killSwitchOn() : apiClient.killSwitchOff(),
        applyOptimistic: () => settings = settings.copyWith(killSwitch: enable),
        success: enable ? 'Kill Switch enabled' : 'Kill Switch disabled',
      );

  Future<String> _toggleSetting({
    required SettingKey key,
    required Future<OpsSettings> Function() updater,
    required VoidCallback applyOptimistic,
    required String success,
  }) async {
    final previous = settings;
    pendingSettings.add(key);
    applyOptimistic();
    notifyListeners();
    try {
      settings = await updater();
      connectionStatus = BackendConnectionStatus.connected;
      bannerWarning = null;
      lastSettingsSyncAt = DateTime.now();
      lastActionAt = DateTime.now();
      lastActionMessage = '$success at ${_clock(lastActionAt!)}';
      return success;
    } on ApiException catch (e) {
      settings = previous;
      if (e.notImplemented) unavailableControls.add(key);
      final msg = 'Failed to update ${_name(key)}: ${e.message}';
      bannerWarning = msg;
      connectionStatus = e.message.contains('unreachable') ? BackendConnectionStatus.offline : BackendConnectionStatus.error;
      return msg;
    } catch (e) {
      settings = previous;
      final msg = 'Failed to update ${_name(key)}: $e';
      bannerWarning = msg;
      connectionStatus = BackendConnectionStatus.error;
      return msg;
    } finally {
      pendingSettings.remove(key);
      notifyListeners();
    }
  }

  String _name(SettingKey key) {
    switch (key) {
      case SettingKey.scheduler:
        return 'scheduler';
      case SettingKey.bot:
        return 'bot';
      case SettingKey.dryRun:
        return 'dry run';
      case SettingKey.killSwitch:
        return 'kill switch';
    }
  }

  String _clock(DateTime dt) =>
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}
