import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../models/candidate.dart';
import '../../models/kis_manual_order_result.dart';
import '../../models/market_watchlist.dart';
import '../../models/manual_trading_run_result.dart';
import '../../models/ops_settings.dart';
import '../../models/order_validation_result.dart';
import '../../models/portfolio_summary.dart';
import '../../models/scheduler_status.dart';
import '../../models/trading_run.dart';
import '../../models/watchlist_run_result.dart';

const _emptyRunResult = WatchlistRunResult(
  configuredSymbolCount: 0,
  analyzedSymbolCount: 0,
  quantCandidatesCount: 0,
  researchedCandidatesCount: 0,
  finalBestCandidate: '',
  secondFinalCandidate: '',
  tiedFinalCandidates: [],
  nearTiedCandidates: [],
  tieBreakerApplied: false,
  finalCandidateSelectionReason: '',
  bestScore: 0,
  finalScoreGap: 0,
  minEntryScore: 0,
  minScoreGap: 0,
  shouldTrade: false,
  triggeredSymbol: null,
  triggerBlockReason: '',
  finalEntryReady: false,
  finalActionHint: 'watch',
  action: '',
  orderId: null,
  topQuantCandidates: [],
  researchedCandidates: [],
  finalRankedCandidates: [],
  result: '',
  reason: '',
  triggerSource: '',
);

class ActionResult {
  const ActionResult({required this.success, required this.message});

  final bool success;
  final String message;
}

enum PortfolioMarket { us, kr }

enum SelectedProvider { alpaca, kis }

class DashboardController extends ChangeNotifier {
  DashboardController(this.apiClient, {bool autoload = true}) {
    if (autoload) {
      load();
    }
  }

  final ApiClient apiClient;

  OpsSettings settings = const OpsSettings(
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
  SchedulerStatus schedulerStatus = SchedulerStatus.safeDefault();

  WatchlistRunResult runResult = _emptyRunResult;
  PortfolioSummary usPortfolioSummary = PortfolioSummary.empty(currency: 'USD');
  PortfolioSummary krPortfolioSummary = PortfolioSummary.empty(currency: 'KRW');
  PortfolioMarket selectedPortfolioMarket = PortfolioMarket.us;
  SelectedProvider selectedProvider = SelectedProvider.alpaca;
  int selectedGateLevel = 2;
  PortfolioMarket selectedOrderMarket = PortfolioMarket.us;
  PortfolioMarket selectedWatchlistMarket = PortfolioMarket.us;
  bool krPortfolioUnavailable = false;
  String? krPortfolioError;
  MarketWatchlist usWatchlist = MarketWatchlist.empty('US');
  MarketWatchlist krWatchlist = MarketWatchlist.empty('KR');
  bool watchlistLoading = false;
  String? watchlistError;
  bool krWatchlistPreviewLoading = false;
  WatchlistRunResult? krWatchlistPreview;
  String? krWatchlistPreviewError;
  String orderTicketSymbol = '005930';
  String orderTicketSide = 'buy';
  int orderTicketQty = 1;
  bool orderValidationLoading = false;
  OrderValidationResult? orderValidationResult;
  String? orderValidationError;
  bool kisLiveConfirmation = false;
  bool kisManualSubmitLoading = false;
  bool kisOrderSyncLoading = false;
  bool kisOrdersLoading = false;
  String? kisManualOrderError;
  KisManualOrderResult? latestKisManualOrder;
  List<KisManualOrderResult> kisOrders = const [];

  PortfolioSummary get portfolioSummary => usPortfolioSummary;

  PortfolioSummary get selectedPortfolioSummary =>
      selectedPortfolioMarket == PortfolioMarket.kr
          ? krPortfolioSummary
          : usPortfolioSummary;

  bool get selectedPortfolioUnavailable =>
      selectedPortfolioMarket == PortfolioMarket.kr && krPortfolioUnavailable;

  List<TradingRun> recentRuns = const [];
  String? error;
  bool hasLatestRunResult = false;
  bool showingOfflineFallback = false;
  bool loading = false;
  bool schedulerLoading = false;
  bool botLoading = false;
  bool killSwitchLoading = false;
  bool runOnceLoading = false;
  bool manualRunLoading = false;
  String? manualRunSymbol;
  ManualTradingRunResult? manualRunResult;

  Future<void> load() async {
    loading = true;
    notifyListeners();
    try {
      settings = await apiClient.getOpsSettings();
      selectedGateLevel = _safeGateLevel(settings.defaultGateLevel);
      schedulerStatus = await apiClient.fetchSchedulerStatus();
      await loadMarketWatchlists();
      await _refreshPortfolioSummaries();
      try {
        final latestRun = await apiClient.fetchLatestWatchlistRunResult();
        if (latestRun == null) {
          runResult = _emptyRunResult;
          hasLatestRunResult = false;
          showingOfflineFallback = false;
        } else {
          runResult = latestRun;
          hasLatestRunResult = true;
          showingOfflineFallback = false;
        }
        error = null;
      } catch (_) {
        if (!hasLatestRunResult) {
          runResult = apiClient.getMockRunResult();
          showingOfflineFallback = true;
        }
        error = showingOfflineFallback
            ? 'Backend latest watchlist run unavailable; showing offline sample data.'
            : 'Backend latest watchlist run unavailable; keeping current result.';
      }
      recentRuns = await apiClient.getRecentTradingRuns();
    } catch (e) {
      error = e.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runOnce() async {
    runOnceLoading = true;
    error = null;
    notifyListeners();
    try {
      final result = await apiClient.runWatchlistForProvider(
        provider: selectedProvider == SelectedProvider.kis ? 'kis' : 'alpaca',
        gateLevel: selectedGateLevel,
      );
      runResult = result;
      hasLatestRunResult = true;
      showingOfflineFallback = false;
      recentRuns = await apiClient.getRecentTradingRuns();
      await _refreshPortfolioSummaries();
      return ActionResult(
          success: true, message: 'Watchlist analysis completed.');
    } catch (e) {
      error = 'Run request failed: $e';
      return ActionResult(success: false, message: error!);
    } finally {
      runOnceLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runTradingOnce({
    required String symbol,
    required int gateLevel,
  }) async {
    final normalizedSymbol = symbol.trim().toUpperCase();
    manualRunLoading = true;
    manualRunSymbol = normalizedSymbol;
    error = null;
    notifyListeners();
    try {
      final result = await apiClient.runTradingOnce(
          symbol: normalizedSymbol, gateLevel: gateLevel);
      manualRunResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      await _refreshPortfolioSummaries();
      final action = result.action.toUpperCase();
      final orderText =
          result.noOrderCreated ? 'no order created' : 'order created';
      return ActionResult(
          success: true, message: 'Manual run completed: $action - $orderText');
    } catch (e) {
      error = e.toString();
      return ActionResult(success: false, message: error!);
    } finally {
      manualRunLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> toggleScheduler(bool v) async {
    final previousSettings = settings;
    settings = OpsSettings(
      schedulerEnabled: v,
      botEnabled: settings.botEnabled,
      dryRun: settings.dryRun,
      killSwitch: settings.killSwitch,
      brokerMode: settings.brokerMode,
      defaultGateLevel: settings.defaultGateLevel,
      maxDailyTrades: settings.maxDailyTrades,
      maxDailyEntries: settings.maxDailyEntries,
      minEntryScore: settings.minEntryScore,
      minScoreGap: settings.minScoreGap,
    );
    schedulerLoading = true;
    error = null;
    notifyListeners();

    try {
      v ? await apiClient.schedulerOn() : await apiClient.schedulerOff();
      settings = await apiClient.getOpsSettings();
      schedulerStatus = await apiClient.fetchSchedulerStatus();
      return ActionResult(
          success: true,
          message: 'Scheduler ${v ? 'enabled' : 'disabled'} successfully.');
    } catch (e) {
      settings = previousSettings;
      error = 'Scheduler call failed: $e';
      return ActionResult(success: false, message: error!);
    } finally {
      schedulerLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> toggleBot(bool v) async {
    final previousSettings = settings;
    settings = OpsSettings(
      schedulerEnabled: settings.schedulerEnabled,
      botEnabled: v,
      dryRun: settings.dryRun,
      killSwitch: settings.killSwitch,
      brokerMode: settings.brokerMode,
      defaultGateLevel: settings.defaultGateLevel,
      maxDailyTrades: settings.maxDailyTrades,
      maxDailyEntries: settings.maxDailyEntries,
      minEntryScore: settings.minEntryScore,
      minScoreGap: settings.minScoreGap,
    );
    botLoading = true;
    error = null;
    notifyListeners();

    try {
      v ? await apiClient.botOn() : await apiClient.botOff();
      settings = await apiClient.getOpsSettings();
      return ActionResult(
          success: true,
          message: 'Bot ${v ? 'enabled' : 'disabled'} successfully.');
    } catch (e) {
      settings = previousSettings;
      error = 'Bot call failed: $e';
      return ActionResult(success: false, message: error!);
    } finally {
      botLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> toggleKillSwitch(bool v) async {
    final previousSettings = settings;
    settings = OpsSettings(
      schedulerEnabled: settings.schedulerEnabled,
      botEnabled: settings.botEnabled,
      dryRun: settings.dryRun,
      killSwitch: v,
      brokerMode: settings.brokerMode,
      defaultGateLevel: settings.defaultGateLevel,
      maxDailyTrades: settings.maxDailyTrades,
      maxDailyEntries: settings.maxDailyEntries,
      minEntryScore: settings.minEntryScore,
      minScoreGap: settings.minScoreGap,
    );
    killSwitchLoading = true;
    error = null;
    notifyListeners();

    try {
      v ? await apiClient.killSwitchOn() : await apiClient.killSwitchOff();
      settings = await apiClient.getOpsSettings();
      return ActionResult(
          success: true,
          message: 'Kill switch ${v ? 'enabled' : 'disabled'} successfully.');
    } catch (e) {
      settings = previousSettings;
      error = 'Kill switch call failed: $e';
      return ActionResult(success: false, message: error!);
    } finally {
      killSwitchLoading = false;
      notifyListeners();
    }
  }

  void setDryRun(bool v) {
    settings = OpsSettings(
      schedulerEnabled: settings.schedulerEnabled,
      botEnabled: settings.botEnabled,
      dryRun: v,
      killSwitch: settings.killSwitch,
      brokerMode: settings.brokerMode,
      defaultGateLevel: settings.defaultGateLevel,
      maxDailyTrades: settings.maxDailyTrades,
      maxDailyEntries: settings.maxDailyEntries,
      minEntryScore: settings.minEntryScore,
      minScoreGap: settings.minScoreGap,
    );
    notifyListeners();
  }

  void selectPortfolioMarket(PortfolioMarket market) {
    if (selectedPortfolioMarket == market) return;
    selectedPortfolioMarket = market;
    notifyListeners();
  }

  void setProvider(SelectedProvider provider) {
    if (selectedProvider == provider) return;
    selectedProvider = provider;
    final market = provider == SelectedProvider.kis
        ? PortfolioMarket.kr
        : PortfolioMarket.us;
    selectedPortfolioMarket = market;
    selectedWatchlistMarket = market;
    selectedOrderMarket = market;
    runResult = _emptyRunResult;
    manualRunResult = null;
    krWatchlistPreview = null;
    notifyListeners();
  }

  void selectOrderMarket(PortfolioMarket market) {
    if (selectedOrderMarket == market) return;
    selectedOrderMarket = market;
    orderValidationError = null;
    notifyListeners();
  }

  void selectWatchlistMarket(PortfolioMarket market) {
    if (selectedWatchlistMarket == market) return;
    selectedWatchlistMarket = market;
    notifyListeners();
  }

  void setOrderTicketSymbol(String value) {
    orderTicketSymbol = value.trim();
    notifyListeners();
  }

  void setOrderTicketSide(String value) {
    orderTicketSide = value.trim().toLowerCase() == 'sell' ? 'sell' : 'buy';
    notifyListeners();
  }

  void setOrderTicketQty(int value) {
    orderTicketQty = value <= 0 ? 1 : value;
    notifyListeners();
  }

  void setKisLiveConfirmation(bool value) {
    kisLiveConfirmation = value;
    notifyListeners();
  }

  void useKrCandidateInOrderTicket(Candidate candidate) {
    selectedOrderMarket = PortfolioMarket.kr;
    orderTicketSymbol = candidate.symbol.trim();
    orderTicketSide = 'buy';
    if (orderTicketQty <= 0) {
      orderTicketQty = 1;
    }
    orderValidationResult = null;
    orderValidationError = null;
    notifyListeners();
  }

  Future<void> loadMarketWatchlists() async {
    watchlistLoading = true;
    watchlistError = null;
    notifyListeners();
    try {
      usWatchlist = await apiClient.fetchMarketWatchlist('US');
      krWatchlist = await apiClient.fetchMarketWatchlist('KR');
    } catch (e) {
      watchlistError = 'Watchlists unavailable: $e';
    } finally {
      watchlistLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> validateKisOrder() async {
    final symbol = orderTicketSymbol.trim();
    final side = orderTicketSide;
    final qty = orderTicketQty;
    orderValidationLoading = true;
    orderValidationError = null;
    orderValidationResult = null;
    notifyListeners();
    try {
      final result = await apiClient.validateKisOrder(
        symbol: symbol,
        side: side,
        qty: qty,
      );
      orderValidationResult = result;
      final status = result.validatedForSubmission
          ? 'Dry-run validated. No real order submitted.'
          : 'Blocked by validation. No real order submitted.';
      return ActionResult(success: true, message: status);
    } catch (e) {
      orderValidationError = e.toString();
      return ActionResult(success: false, message: orderValidationError!);
    } finally {
      orderValidationLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> submitKisManualOrder() async {
    if (!kisLiveConfirmation) {
      return const ActionResult(
        success: false,
        message: 'Live confirmation is required before submitting.',
      );
    }

    kisManualSubmitLoading = true;
    kisManualOrderError = null;
    notifyListeners();

    try {
      var result = await apiClient.submitKisManualOrder(
        symbol: orderTicketSymbol,
        side: orderTicketSide,
        qty: orderTicketQty,
        orderType: 'market',
        confirmLive: kisLiveConfirmation,
      );
      latestKisManualOrder = result;
      _upsertKisOrder(result);

      try {
        result = await apiClient.syncKisOrder(result.orderId);
        latestKisManualOrder = result;
        _upsertKisOrder(result);
      } catch (e) {
        kisManualOrderError = 'Submitted; status sync unavailable: $e';
      }

      await _refreshKisOrdersAfterAction();
      return ActionResult(
        success: true,
        message:
            'Live KIS order submitted. Status: ${latestKisManualOrder?.internalStatus ?? result.internalStatus}.',
      );
    } catch (e) {
      kisManualOrderError = e.toString();
      return ActionResult(success: false, message: kisManualOrderError!);
    } finally {
      kisManualSubmitLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> syncLatestKisOrder() async {
    final order =
        latestKisManualOrder ?? (kisOrders.isEmpty ? null : kisOrders.first);
    if (order == null) {
      return const ActionResult(
        success: false,
        message: 'No KIS order is available to sync.',
      );
    }

    kisOrderSyncLoading = true;
    kisManualOrderError = null;
    notifyListeners();

    try {
      final result = await apiClient.syncKisOrder(order.orderId);
      latestKisManualOrder = result;
      _upsertKisOrder(result);
      await _refreshKisOrdersAfterAction();
      return ActionResult(
        success: true,
        message: 'KIS order status synced: ${result.internalStatus}.',
      );
    } catch (e) {
      kisManualOrderError = e.toString();
      return ActionResult(success: false, message: kisManualOrderError!);
    } finally {
      kisOrderSyncLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisOrders() async {
    kisOrdersLoading = true;
    kisManualOrderError = null;
    notifyListeners();
    try {
      kisOrders = await apiClient.fetchKisOrders();
      latestKisManualOrder =
          kisOrders.isEmpty ? latestKisManualOrder : kisOrders.first;
      return const ActionResult(
          success: true, message: 'KIS orders refreshed.');
    } catch (e) {
      kisManualOrderError = e.toString();
      return ActionResult(success: false, message: kisManualOrderError!);
    } finally {
      kisOrdersLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKrWatchlistPreview() async {
    krWatchlistPreviewLoading = true;
    krWatchlistPreviewError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisWatchlistPreview(
        gateLevel: selectedGateLevel,
      );
      krWatchlistPreview = result;
      return const ActionResult(
        success: true,
        message: 'KR preview completed. No real order submitted.',
      );
    } catch (e) {
      krWatchlistPreviewError = 'KR preview failed: $e';
      return ActionResult(success: false, message: krWatchlistPreviewError!);
    } finally {
      krWatchlistPreviewLoading = false;
      notifyListeners();
    }
  }

  Future<void> _refreshPortfolioSummaries() async {
    await _refreshUsPortfolioSummary();
    await _refreshKrPortfolioSummary();
  }

  Future<void> _refreshUsPortfolioSummary() async {
    try {
      usPortfolioSummary = await apiClient.fetchUsPortfolioSummary();
    } catch (_) {
      // Keep the last live snapshot if the backend returns a transient error.
    }
  }

  Future<void> _refreshKrPortfolioSummary() async {
    try {
      krPortfolioSummary = await apiClient.fetchKrPortfolioSummary();
      krPortfolioUnavailable = false;
      krPortfolioError = null;
    } catch (_) {
      krPortfolioSummary = PortfolioSummary.empty(currency: 'KRW');
      krPortfolioUnavailable = true;
      krPortfolioError = 'KIS account data unavailable';
    }
  }

  void setSelectedGateLevel(int gateLevel) {
    selectedGateLevel = _safeGateLevel(gateLevel);
    notifyListeners();
  }

  int _safeGateLevel(int value) => (value >= 1 && value <= 4) ? value : 2;

  Future<void> _refreshKisOrdersAfterAction() async {
    try {
      kisOrders = await apiClient.fetchKisOrders();
      if (kisOrders.isNotEmpty) {
        latestKisManualOrder = kisOrders.first;
      }
    } catch (_) {
      // Keep the submitted/synced order visible if list refresh is unavailable.
    }
  }

  void _upsertKisOrder(KisManualOrderResult order) {
    final updated = <KisManualOrderResult>[];
    var inserted = false;
    for (final existing in kisOrders) {
      if (existing.orderId == order.orderId) {
        updated.add(order);
        inserted = true;
      } else {
        updated.add(existing);
      }
    }
    if (!inserted) {
      updated.insert(0, order);
    }
    kisOrders = updated;
  }
}
