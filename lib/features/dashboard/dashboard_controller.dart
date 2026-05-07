import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../core/network/api_error_formatter.dart';
import '../../models/candidate.dart';
import '../../models/kis_manual_order_result.dart';
import '../../models/kis_manual_order_safety_status.dart';
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

enum KisOrderHistoryFilter { open, filled, canceled, rejected, all }

enum KisOrderHistorySort { newestFirst, oldestFirst }

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
  bool kisOrderCancelLoading = false;
  bool kisOrdersLoading = false;
  bool kisSafetyStatusLoading = false;
  KisManualOrderSafetyStatus kisSafetyStatus =
      KisManualOrderSafetyStatus.safeDefault;
  String? kisManualOrderError;
  String? kisManualOrderErrorRaw;
  KisManualOrderResult? latestKisManualOrder;
  List<KisManualOrderResult> kisOrders = const [];
  KisOrderSummary kisOrderSummary = KisOrderSummary.empty;
  bool kisIncludeRejected = false;
  KisOrderHistoryFilter kisOrderFilter = KisOrderHistoryFilter.all;
  KisOrderHistorySort kisOrderSort = KisOrderHistorySort.newestFirst;
  KisManualOrderResult? selectedKisOrder;

  bool get hasValidKisValidation =>
      orderValidationResult?.validatedForSubmission == true;

  bool get isOrderTicketInputValid =>
      orderTicketSymbol.trim().isNotEmpty && orderTicketQty > 0;

  bool get canSubmitLiveKisOrder {
    final validation = orderValidationResult;
    if (validation == null) return false;

    final symbolMatches = validation.symbol == orderTicketSymbol.trim();
    final qtyMatches = validation.qty == orderTicketQty;
    final sideMatches = validation.side == orderTicketSide;

    return !kisManualSubmitLoading &&
        validation.validatedForSubmission &&
        isOrderTicketInputValid &&
        symbolMatches &&
        qtyMatches &&
        sideMatches &&
        kisLiveConfirmation &&
        !kisSafetyStatus.runtimeDryRun &&
        !kisSafetyStatus.killSwitch &&
        kisSafetyStatus.kisEnabled &&
        kisSafetyStatus.kisRealOrderEnabled &&
        kisSafetyStatus.marketOpen &&
        kisSafetyStatus.entryAllowedNow;
  }

  PortfolioSummary get portfolioSummary => usPortfolioSummary;

  PortfolioSummary get selectedPortfolioSummary =>
      selectedPortfolioMarket == PortfolioMarket.kr
          ? krPortfolioSummary
          : usPortfolioSummary;

  bool get selectedPortfolioUnavailable =>
      selectedPortfolioMarket == PortfolioMarket.kr && krPortfolioUnavailable;
  List<KisManualOrderResult> get visibleKisOrders {
    final filtered = kisOrders.where(_matchesKisOrderFilter).toList();
    filtered.sort((a, b) {
      final aTime = _createdAtForSort(a);
      final bTime = _createdAtForSort(b);
      final compare = aTime.compareTo(bTime);
      if (compare != 0) {
        return kisOrderSort == KisOrderHistorySort.newestFirst
            ? -compare
            : compare;
      }
      return kisOrderSort == KisOrderHistorySort.newestFirst
          ? b.orderId.compareTo(a.orderId)
          : a.orderId.compareTo(b.orderId);
    });
    return filtered;
  }

  bool get selectedKisOrderIsPollable => _isPollableKisOrder(selectedKisOrder);

  List<TradingRun> recentRuns = const [];
  String? error;
  bool hasLatestRunResult = false;
  bool showingOfflineFallback = false;
  bool loading = false;
  bool schedulerLoading = false;
  bool botLoading = false;
  bool killSwitchLoading = false;
  bool dryRunLoading = false;
  bool runOnceLoading = false;
  bool manualRunLoading = false;
  String? manualRunSymbol;
  ManualTradingRunResult? manualRunResult;

  Future<void> load() async {
    loading = true;
    notifyListeners();
    try {
      settings = await apiClient.getOpsSettings();
      kisSafetyStatus = kisSafetyStatusFromSettings();
      await refreshKisSafetyStatus(silent: true);
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
      kisSafetyStatus = kisSafetyStatusFromSettings();
      await refreshKisSafetyStatus(silent: true);
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

  Future<ActionResult> setDryRun(bool v) async {
    final previousSettings = settings;
    settings = settings.copyWith(dryRun: v);
    dryRunLoading = true;
    error = null;
    notifyListeners();

    try {
      await apiClient.updateOpsSettings({'dry_run': v});
      settings = await apiClient.getOpsSettings();
      kisSafetyStatus = kisSafetyStatusFromSettings();
      await refreshKisSafetyStatus(silent: true);
      return ActionResult(
          success: true,
          message:
              'Dry run ${settings.dryRun ? 'enabled' : 'disabled'} successfully.');
    } catch (e) {
      settings = previousSettings;
      error =
          'Dry run update failed: ${ApiErrorFormatter.format(e.toString())}';
      return ActionResult(success: false, message: error!);
    } finally {
      dryRunLoading = false;
      notifyListeners();
    }
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
    if (provider == SelectedProvider.kis) {
      refreshKisOrderMonitoring(silent: true);
    }
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

  KisManualOrderSafetyStatus kisSafetyStatusFromSettings() {
    return KisManualOrderSafetyStatus(
      runtimeDryRun: settings.dryRun,
      killSwitch: settings.killSwitch,
      kisEnabled: kisSafetyStatus.kisEnabled,
      kisRealOrderEnabled: kisSafetyStatus.kisRealOrderEnabled,
      marketOpen: kisSafetyStatus.marketOpen,
      entryAllowedNow: kisSafetyStatus.entryAllowedNow,
      noNewEntryAfter: kisSafetyStatus.noNewEntryAfter,
    );
  }

  Future<ActionResult> refreshKisSafetyStatus({bool silent = false}) async {
    kisSafetyStatusLoading = true;
    if (!silent) notifyListeners();
    try {
      kisSafetyStatus = await apiClient.fetchKisManualOrderSafetyStatus();
      settings = settings.copyWith(
        dryRun: kisSafetyStatus.runtimeDryRun,
        killSwitch: kisSafetyStatus.killSwitch,
      );
      return const ActionResult(
        success: true,
        message: 'KIS safety status refreshed.',
      );
    } catch (e) {
      kisSafetyStatus = kisSafetyStatusFromSettings();
      return ActionResult(
        success: false,
        message: _primaryMessage(ApiErrorFormatter.format(e.toString())),
      );
    } finally {
      kisSafetyStatusLoading = false;
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
      await refreshKisSafetyStatus(silent: true);
      final result = await apiClient.validateKisOrder(
        symbol: symbol,
        side: side,
        qty: qty,
      );
      orderValidationResult = result;
      final status = result.validatedForSubmission
          ? 'Dry-run validated. No real order submitted.'
          : result.message ?? 'Blocked by validation. No real order submitted.';
      return ActionResult(success: true, message: status);
    } catch (e) {
      orderValidationError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
          success: false, message: _primaryMessage(orderValidationError!));
    } finally {
      orderValidationLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> submitKisManualOrder() async {
    await refreshKisSafetyStatus(silent: true);

    if (!canSubmitLiveKisOrder) {
      return ActionResult(
        success: false,
        message: kisSubmitBlockedMessage(),
      );
    }

    if (!kisLiveConfirmation) {
      return const ActionResult(
        success: false,
        message: 'Live confirmation is required before submitting.',
      );
    }

    kisManualSubmitLoading = true;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
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
        kisManualOrderError =
            'Submitted; status sync unavailable: ${ApiErrorFormatter.format(e.toString())}';
        kisManualOrderErrorRaw = e.toString();
      }

      await _refreshKisOrdersAfterAction();
      return ActionResult(
        success: true,
        message: _submittedMessage(latestKisManualOrder ?? result),
      );
    } catch (e) {
      kisManualOrderError = ApiErrorFormatter.format(e.toString());
      kisManualOrderErrorRaw = e.toString();
      return ActionResult(
          success: false, message: _primaryMessage(kisManualOrderError!));
    } finally {
      kisManualSubmitLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> syncLatestKisOrder() async {
    if (kisOrderSyncLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS sync already in progress.',
      );
    }
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
    kisManualOrderErrorRaw = null;
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
      kisManualOrderError = ApiErrorFormatter.format(e.toString());
      kisManualOrderErrorRaw = e.toString();
      return ActionResult(
          success: false, message: _primaryMessage(kisManualOrderError!));
    } finally {
      kisOrderSyncLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> syncKisOrderById(int orderId) async {
    if (kisOrderSyncLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS sync already in progress.',
      );
    }

    kisOrderSyncLoading = true;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    notifyListeners();

    try {
      final result = await apiClient.syncKisOrder(orderId);
      latestKisManualOrder = result;
      selectedKisOrder = result;
      _upsertKisOrder(result);
      await _refreshKisOrdersAfterAction(preferredOrderId: result.orderId);
      return ActionResult(
        success: true,
        message: 'KIS order status synced: ${result.internalStatus}.',
      );
    } catch (e) {
      kisManualOrderError = ApiErrorFormatter.format(e.toString());
      kisManualOrderErrorRaw = e.toString();
      return ActionResult(
          success: false, message: _primaryMessage(kisManualOrderError!));
    } finally {
      kisOrderSyncLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisOrders() async {
    kisOrdersLoading = true;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    notifyListeners();
    try {
      kisOrders = await apiClient.fetchKisOrders(includeRejected: true);
      latestKisManualOrder =
          kisOrders.isEmpty ? latestKisManualOrder : kisOrders.first;
      selectedKisOrder = _selectedOrderFromList(selectedKisOrder?.orderId);
      _alignSelectedKisOrderWithVisible();
      await _refreshKisOrderSummary();
      return const ActionResult(
          success: true, message: 'KIS orders refreshed.');
    } catch (e) {
      kisManualOrderError = ApiErrorFormatter.format(e.toString());
      kisManualOrderErrorRaw = e.toString();
      return ActionResult(
          success: false, message: _primaryMessage(kisManualOrderError!));
    } finally {
      kisOrdersLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> syncOpenKisOrders() async {
    if (kisOrderSyncLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS sync already in progress.',
      );
    }

    kisOrderSyncLoading = true;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    notifyListeners();

    try {
      final result = await apiClient.syncOpenKisOrders();
      await _refreshKisOrdersAfterAction();
      final count = result.count;
      return ActionResult(
        success: true,
        message: count == null
            ? 'Open KIS orders synced.'
            : 'Open KIS orders synced: $count updated.',
      );
    } catch (e) {
      kisManualOrderError = ApiErrorFormatter.format(e.toString());
      kisManualOrderErrorRaw = e.toString();
      return ActionResult(
          success: false, message: _primaryMessage(kisManualOrderError!));
    } finally {
      kisOrderSyncLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> cancelKisOrderById(int orderId) async {
    if (kisOrderCancelLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS cancel already in progress.',
      );
    }

    kisOrderCancelLoading = true;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    notifyListeners();

    try {
      final payload = await apiClient.cancelKisOrder(orderId);
      final canceled = payload['canceled'] == true;
      final message = _payloadMessage(
        payload,
        canceled ? 'KIS order canceled.' : 'KIS order was not canceled.',
      );
      try {
        final detail = await apiClient.fetchKisOrderDetail(orderId);
        latestKisManualOrder = detail;
        selectedKisOrder = detail;
        _upsertKisOrder(detail);
      } catch (_) {
        // The recent-orders refresh below still keeps the list current.
      }
      await _refreshKisOrdersAfterAction(preferredOrderId: orderId);
      return ActionResult(success: canceled, message: message);
    } catch (e) {
      kisManualOrderError = ApiErrorFormatter.format(e.toString());
      kisManualOrderErrorRaw = e.toString();
      return ActionResult(
          success: false, message: _primaryMessage(kisManualOrderError!));
    } finally {
      kisOrderCancelLoading = false;
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

  Future<void> refreshKisOrderMonitoring({bool silent = false}) async {
    if (kisOrdersLoading) return;
    kisOrdersLoading = true;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    if (!silent) notifyListeners();
    try {
      kisOrders = await apiClient.fetchKisOrders(includeRejected: true);
      latestKisManualOrder =
          kisOrders.isEmpty ? latestKisManualOrder : kisOrders.first;
      selectedKisOrder = _selectedOrderFromList(selectedKisOrder?.orderId);
      _alignSelectedKisOrderWithVisible();
      await _refreshKisOrderSummary();
    } catch (e) {
      kisManualOrderError = ApiErrorFormatter.format(e.toString());
      kisManualOrderErrorRaw = e.toString();
    } finally {
      kisOrdersLoading = false;
      notifyListeners();
    }
  }

  Future<void> pollSelectedKisOrder() async {
    final order = selectedKisOrder;
    if (!_isPollableKisOrder(order) || kisOrderSyncLoading) return;
    await syncKisOrderById(order!.orderId);
  }

  Future<void> _refreshKisOrdersAfterAction({int? preferredOrderId}) async {
    try {
      kisOrders = await apiClient.fetchKisOrders(includeRejected: true);
      if (kisOrders.isNotEmpty) {
        latestKisManualOrder = kisOrders.first;
        selectedKisOrder = _selectedOrderFromList(
            preferredOrderId ?? selectedKisOrder?.orderId);
        _alignSelectedKisOrderWithVisible();
      }
      await _refreshKisOrderSummary();
    } catch (_) {
      // Keep the submitted/synced order visible if list refresh is unavailable.
    }
  }

  Future<void> _refreshKisOrderSummary() async {
    try {
      kisOrderSummary = await apiClient.fetchKisOrderSummary();
    } catch (_) {
      // Keep the last summary visible if this lightweight endpoint is unavailable.
    }
  }

  KisManualOrderResult? _selectedOrderFromList(int? preferredOrderId) {
    if (kisOrders.isEmpty) return latestKisManualOrder;
    if (preferredOrderId != null) {
      for (final order in kisOrders) {
        if (order.orderId == preferredOrderId) {
          return order;
        }
      }
    }
    return selectedKisOrder ?? latestKisManualOrder ?? kisOrders.first;
  }

  void _alignSelectedKisOrderWithVisible() {
    final visible = visibleKisOrders;
    if (visible.isEmpty) {
      selectedKisOrder = null;
      return;
    }
    final selectedId = selectedKisOrder?.orderId;
    if (selectedId != null &&
        visible.any((order) => order.orderId == selectedId)) {
      return;
    }
    selectedKisOrder = visible.first;
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
    selectedKisOrder = order;
  }

  Future<void> setKisIncludeRejected(bool value) async {
    kisIncludeRejected = value;
    await refreshKisOrders();
  }

  void setKisOrderFilter(KisOrderHistoryFilter filter) {
    if (kisOrderFilter == filter) return;
    kisOrderFilter = filter;
    _alignSelectedKisOrderWithVisible();
    notifyListeners();
  }

  void setKisOrderSort(KisOrderHistorySort sort) {
    if (kisOrderSort == sort) return;
    kisOrderSort = sort;
    _alignSelectedKisOrderWithVisible();
    notifyListeners();
  }

  String kisSubmitBlockedMessage() {
    final validation = orderValidationResult;
    if (validation == null || !validation.validatedForSubmission) {
      return 'Run a successful validation first.';
    }

    final symbolMatches = validation.symbol == orderTicketSymbol.trim();
    final qtyMatches = validation.qty == orderTicketQty;
    final sideMatches = validation.side == orderTicketSide;
    if (!symbolMatches || !qtyMatches || !sideMatches) {
      return 'Current order input changed after validation. Validate again.';
    }

    if (!kisLiveConfirmation) return 'Confirm live KIS order first.';
    if (kisSafetyStatus.runtimeDryRun) return 'Backend dry-run is ON.';
    if (kisSafetyStatus.killSwitch) return 'Kill switch is ON.';
    if (!kisSafetyStatus.kisEnabled) return 'KIS trading is disabled.';
    if (!kisSafetyStatus.kisRealOrderEnabled) {
      return 'KIS real-order submission is disabled.';
    }
    if (!kisSafetyStatus.marketOpen) return 'Market is closed.';
    if (!kisSafetyStatus.entryAllowedNow) {
      return 'Market entry is not allowed now.';
    }
    if (!isOrderTicketInputValid) return 'Enter a valid symbol and quantity.';
    return 'Live KIS submit is blocked by the checklist.';
  }

  Future<void> selectKisOrder(int orderId) async {
    try {
      selectedKisOrder = await apiClient.fetchKisOrderDetail(orderId);
      notifyListeners();
    } catch (_) {}
  }

  bool _matchesKisOrderFilter(KisManualOrderResult order) {
    switch (kisOrderFilter) {
      case KisOrderHistoryFilter.open:
        return order.isSyncable && !order.isTerminal;
      case KisOrderHistoryFilter.filled:
        return order.clearStatusLabel == 'FILLED';
      case KisOrderHistoryFilter.canceled:
        return order.clearStatusLabel == 'CANCELED';
      case KisOrderHistoryFilter.rejected:
        return order.clearStatusLabel == 'REJECTED';
      case KisOrderHistoryFilter.all:
        return true;
    }
  }
}

String _primaryMessage(String value) {
  final lines = value
      .split(RegExp(r'[\r\n]+'))
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty);
  return lines.isEmpty ? value.trim() : lines.first;
}

String _payloadMessage(Map<String, dynamic> payload, String fallback) {
  final value = payload['message'];
  if (value is String && value.trim().isNotEmpty) {
    return value.trim();
  }
  return fallback;
}

String _submittedMessage(KisManualOrderResult order) {
  final status = _kisTerminalLabel(order);
  final odno = order.kisOdno == null ? '' : ' / ODNO ${order.kisOdno}';
  return 'Live KIS order ${order.orderId}$odno: $status.';
}

String _kisTerminalLabel(KisManualOrderResult order) {
  return order.clearStatusLabel;
}

DateTime _createdAtForSort(KisManualOrderResult order) {
  final parsed = DateTime.tryParse(order.createdAt ?? '');
  return parsed ?? DateTime.fromMillisecondsSinceEpoch(0);
}

bool _isPollableKisOrder(KisManualOrderResult? order) {
  return order != null && order.isSyncable && !order.isTerminal;
}
