import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../core/network/api_error_formatter.dart';
import '../../models/candidate.dart';
import '../../models/kis_auto_readiness.dart';
import '../../models/kis_auto_simulator_result.dart';
import '../../models/kis_buy_shadow_decision.dart';
import '../../models/kis_exit_shadow_decision.dart';
import '../../models/kis_limited_auto_buy.dart';
import '../../models/kis_limited_auto_buy_execution_review.dart';
import '../../models/kis_limited_auto_buy_review.dart';
import '../../models/kis_limited_auto_sell.dart';
import '../../models/kis_single_symbol_trading_result.dart';
import '../../models/kis_shadow_exit_review.dart';
import '../../models/kis_shadow_exit_review_queue.dart';
import '../../models/kis_live_exit_preflight.dart';
import '../../models/kis_manual_order_result.dart';
import '../../models/kis_manual_order_safety_status.dart';
import '../../models/kis_scheduler_dry_run_orchestration.dart';
import '../../models/kis_scheduler_dry_run_review.dart';
import '../../models/kis_scheduler_guarded_sell.dart';
import '../../models/kis_scheduler_readiness.dart';
import '../../models/kis_scheduler_simulation.dart';
import '../../models/kis_scheduler_live.dart';
import '../../models/market_watchlist.dart';
import '../../models/managed_position.dart';
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
  List<ManagedPosition> kisManagedPositions = const [];
  bool kisManagedPositionsLoading = false;
  String? kisManagedPositionsError;
  ManualSellPreparation? latestManualSellPreparation;
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
  bool kosdaqTop50Updating = false;
  String? kosdaqTop50UpdateError;
  Map<String, dynamic>? latestKosdaqTop50Update;
  bool krWatchlistPreviewLoading = false;
  WatchlistRunResult? krWatchlistPreview;
  String? krWatchlistPreviewError;
  bool kisAutoSimulatorLoading = false;
  KisAutoSimulatorResult? kisAutoSimulatorResult;
  String? kisAutoSimulatorError;
  bool kisSchedulerStatusLoading = false;
  bool kisSchedulerStatusLoaded = false;
  KisSchedulerSimulationStatus kisSchedulerStatus =
      KisSchedulerSimulationStatus.safeDefault();
  String? kisSchedulerStatusError;
  bool kisSchedulerRunLoading = false;
  KisSchedulerRunResult? kisSchedulerRunResult;
  String? kisSchedulerRunError;
  bool kisSchedulerReadinessLoading = false;
  KisSchedulerReadiness? latestKisSchedulerReadiness;
  String? kisSchedulerReadinessError;
  bool kisSchedulerDryRunOrchestrationLoading = false;
  KisSchedulerDryRunOrchestration? latestKisSchedulerDryRunOrchestration;
  String? kisSchedulerDryRunOrchestrationError;
  bool kisSchedulerDryRunReviewLoading = false;
  KisSchedulerDryRunReview? latestKisSchedulerDryRunReview;
  String? kisSchedulerDryRunReviewError;
  bool kisLiveExitPreflightLoading = false;
  KisLiveExitPreflightResult? kisLiveExitPreflightResult;
  String? kisLiveExitPreflightError;
  bool kisExitShadowLoading = false;
  KisExitShadowDecision? latestKisExitShadowDecision;
  String? kisExitShadowError;
  bool kisShadowExitReviewLoading = false;
  KisShadowExitReview? latestKisShadowExitReview;
  String? kisShadowExitReviewError;
  bool kisShadowExitReviewQueueLoading = false;
  KisShadowExitReviewQueue? latestKisShadowExitReviewQueue;
  String? kisShadowExitReviewQueueError;
  bool kisLimitedAutoSellLoading = false;
  KisLimitedAutoSell? latestKisLimitedAutoSellResult;
  String? kisLimitedAutoSellError;
  bool kisBuyShadowLoading = false;
  KisBuyShadowDecision? latestKisBuyShadowDecision;
  String? kisBuyShadowError;
  bool kisLimitedAutoBuyLoading = false;
  KisLimitedAutoBuy? latestKisLimitedAutoBuyResult;
  String? kisLimitedAutoBuyError;
  bool kisLimitedAutoBuyReviewLoading = false;
  KisLimitedAutoBuyReview? latestKisLimitedAutoBuyReview;
  String? kisLimitedAutoBuyReviewError;
  bool kisLimitedAutoBuyExecutionReviewLoading = false;
  KisLimitedAutoBuyExecutionReview? latestKisLimitedAutoBuyExecutionReview;
  String? kisLimitedAutoBuyExecutionReviewError;
  bool kisSingleSymbolTradingLoading = false;
  KisSingleSymbolTradingResult? latestKisSingleSymbolTradingResult;
  String? kisSingleSymbolTradingError;
  bool kisSchedulerLiveLoading = false;
  KisSchedulerLiveResult? latestKisSchedulerLiveResult;
  String? kisSchedulerLiveError;
  bool kisSchedulerGuardedSellLoading = false;
  KisSchedulerGuardedSellResult? latestKisSchedulerGuardedSellResult;
  String? kisSchedulerGuardedSellError;
  bool kisAutoReadinessLoading = false;
  bool kisAutoPreflightLoading = false;
  bool kisAutoReadinessLoaded = false;
  KisAutoReadiness? kisAutoReadinessResult;
  String? kisAutoReadinessError;
  String orderTicketSymbol = '005930';
  String orderTicketSide = 'buy';
  int orderTicketQty = 1;
  String orderTicketQtyInput = '1';
  Map<String, dynamic>? orderTicketSourceMetadata;
  bool orderValidationLoading = false;
  OrderValidationResult? orderValidationResult;
  String? orderValidationError;
  bool kisLiveConfirmation = false;
  bool kisGuardedRunConfirmation = false;
  String kisGuardedRunSymbol = '005930';
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

  int? get parsedOrderTicketQty => _parseOrderTicketQty(orderTicketQtyInput);

  bool get isOrderTicketQtyValid => parsedOrderTicketQty != null;

  bool get isOrderTicketInputValid =>
      orderTicketSymbol.trim().isNotEmpty && isOrderTicketQtyValid;

  bool get hasExitPreflightPreparedSellTicket =>
      orderTicketSourceMetadata?['source'] == 'kis_live_exit_preflight' &&
      orderTicketSide == 'sell';

  bool get hasExitShadowPreparedSellTicket =>
      orderTicketSourceMetadata?['source'] == 'kis_exit_shadow_decision' &&
      orderTicketSide == 'sell';

  bool get hasPreparedKisExitSellTicket =>
      hasExitPreflightPreparedSellTicket || hasExitShadowPreparedSellTicket;

  bool get currentOrderRequiresEntryWindow => orderTicketSide != 'sell';

  bool get kisCurrentOrderRuntimeGatesOpen {
    return !kisSafetyStatus.runtimeDryRun &&
        !kisSafetyStatus.killSwitch &&
        kisSafetyStatus.kisEnabled &&
        kisSafetyStatus.kisRealOrderEnabled &&
        kisSafetyStatus.marketOpen &&
        (!currentOrderRequiresEntryWindow || kisSafetyStatus.entryAllowedNow);
  }

  bool get canSubmitLiveKisOrder {
    final validation = orderValidationResult;
    if (validation == null) return false;

    final symbolMatches = validation.symbol == orderTicketSymbol.trim();
    final currentQty = parsedOrderTicketQty;
    final qtyMatches = currentQty != null && validation.qty == currentQty;
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
        (!currentOrderRequiresEntryWindow || kisSafetyStatus.entryAllowedNow);
  }

  bool get canRunKisGuardedTradingOnce {
    return kisGuardedRunSymbol.trim().isNotEmpty &&
        !kisLimitedAutoBuyLoading &&
        kisRuntimeLiveSubmitGatesOpen &&
        kisGuardedRunConfirmation;
  }

  bool get kisRuntimeLiveSubmitGatesOpen {
    return !kisSafetyStatus.runtimeDryRun &&
        !kisSafetyStatus.killSwitch &&
        kisSafetyStatus.kisEnabled &&
        kisSafetyStatus.kisRealOrderEnabled &&
        kisSafetyStatus.marketOpen &&
        kisSafetyStatus.entryAllowedNow;
  }

  bool get isKisSelected => selectedProvider == SelectedProvider.kis;

  String get selectedProviderCode => isKisSelected ? 'kis' : 'alpaca';

  String get selectedMarketCode => isKisSelected ? 'KR' : 'US';

  String get selectedBrokerLabel => isKisSelected ? 'KIS / KR' : 'Alpaca / US';

  PortfolioSummary get portfolioSummary => usPortfolioSummary;

  PortfolioSummary get selectedPortfolioSummary =>
      selectedPortfolioMarket == PortfolioMarket.kr
          ? krPortfolioSummary
          : usPortfolioSummary;

  bool get selectedPortfolioUnavailable =>
      selectedPortfolioMarket == PortfolioMarket.kr && krPortfolioUnavailable;

  ManagedPosition? kisManagedPositionForSymbol(String symbol) {
    final normalized = symbol.trim().toUpperCase();
    for (final position in kisManagedPositions) {
      if (position.symbol.toUpperCase() == normalized) return position;
    }
    return null;
  }

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
      await refreshKisSchedulerStatus(silent: true);
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
      final immediateResult = await apiClient.runTradingOnce(
          symbol: normalizedSymbol, gateLevel: gateLevel);
      final result = await _enrichManualRunResult(immediateResult);
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

  Future<ManualTradingRunResult> _enrichManualRunResult(
    ManualTradingRunResult result,
  ) async {
    final signalId = result.signalId?.trim();
    if (signalId == null || signalId.isEmpty) return result;

    try {
      final signals = await apiClient.fetchRecentSignalPayloads(limit: 50);
      for (final signal in signals) {
        if (_signalMatchesId(signal, signalId)) {
          return result.mergeSignalPayload(signal);
        }
      }
    } catch (_) {
      // The immediate run response is still useful; only score enrichment failed.
    }

    if (!result.hasScoreDetails) {
      return result.markScoreDetailsNotReturned();
    }
    return result;
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
      kisSafetyStatus = kisSafetyStatusFromSettings();
      final message =
          'Dry run update failed: ${ApiErrorFormatter.format(e.toString())}';
      try {
        settings = await apiClient.getOpsSettings();
        kisSafetyStatus = kisSafetyStatusFromSettings();
        await refreshKisSafetyStatus(silent: true);
      } catch (_) {
        // Keep the rollback state when the backend refresh is unavailable.
      }
      error = message;
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
    latestKisSingleSymbolTradingResult = null;
    kisSingleSymbolTradingError = null;
    kisGuardedRunConfirmation = false;
    kisLiveConfirmation = false;
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
    _clearOrderTicketSourceMetadata();
    notifyListeners();
  }

  void setOrderTicketSide(String value) {
    orderTicketSide = value.trim().toLowerCase() == 'sell' ? 'sell' : 'buy';
    _clearOrderTicketSourceMetadata();
    notifyListeners();
  }

  void setOrderTicketQty(int value) {
    setOrderTicketQtyInput(value.toString());
  }

  void setOrderTicketQtyInput(String value) {
    orderTicketQtyInput = value;
    final parsed = _parseOrderTicketQty(value);
    if (parsed != null) {
      orderTicketQty = parsed;
    }
    _clearOrderTicketSourceMetadata();
    notifyListeners();
  }

  void setKisLiveConfirmation(bool value) {
    kisLiveConfirmation = value;
    notifyListeners();
  }

  void setKisGuardedRunSymbol(String value) {
    kisGuardedRunSymbol = value.trim().toUpperCase();
    kisGuardedRunConfirmation = false;
    latestKisLimitedAutoBuyResult = null;
    kisLimitedAutoBuyError = null;
    latestKisLimitedAutoBuyReview = null;
    kisLimitedAutoBuyReviewError = null;
    latestKisLimitedAutoBuyExecutionReview = null;
    kisLimitedAutoBuyExecutionReviewError = null;
    latestKisSingleSymbolTradingResult = null;
    kisSingleSymbolTradingError = null;
    notifyListeners();
  }

  void setKisGuardedRunConfirmation(bool value) {
    kisGuardedRunConfirmation = value;
    notifyListeners();
  }

  void useKrCandidateInOrderTicket(Candidate candidate) {
    selectedOrderMarket = PortfolioMarket.kr;
    orderTicketSymbol = candidate.symbol.trim();
    orderTicketSide = 'buy';
    if (orderTicketQty <= 0 || parsedOrderTicketQty == null) {
      orderTicketQty = 1;
      orderTicketQtyInput = '1';
    }
    orderValidationResult = null;
    orderValidationError = null;
    kisLiveConfirmation = false;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    orderTicketSourceMetadata = {
      'source': 'watchlist_candidate',
      'source_type': 'manual_buy_ticket_prefill',
      'symbol': candidate.symbol.trim(),
      'score': candidate.score,
      'entry_ready': candidate.entryReady,
      'action_hint': candidate.actionHint,
      'block_reason': candidate.blockReason,
      'risk_flags': candidate.riskFlags,
      'gating_notes': candidate.gatingNotes,
      'manual_confirm_required': true,
      'auto_buy_enabled': false,
      'scheduler_real_order_enabled': false,
      'real_order_submit_allowed': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    };
    notifyListeners();
  }

  ActionResult prepareKisManualBuyTicketFromSymbol(
    String symbol, {
    int? gateLevel,
  }) {
    final normalizedSymbol = symbol.trim().toUpperCase();
    if (normalizedSymbol.isEmpty) {
      return const ActionResult(
        success: false,
        message: 'Enter a KIS symbol before preparing a ticket.',
      );
    }

    selectedOrderMarket = PortfolioMarket.kr;
    orderTicketSymbol = normalizedSymbol;
    orderTicketSide = 'buy';
    if (orderTicketQty <= 0 || parsedOrderTicketQty == null) {
      orderTicketQty = 1;
      orderTicketQtyInput = '1';
    }
    orderValidationResult = null;
    orderValidationError = null;
    kisLiveConfirmation = false;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    orderTicketSourceMetadata = {
      'source': 'single_symbol_trading',
      'source_type': 'manual_buy_ticket_prefill',
      'symbol': normalizedSymbol,
      if (gateLevel != null) 'gate_level': gateLevel,
      'manual_confirm_required': true,
      'auto_buy_enabled': false,
      'scheduler_real_order_enabled': false,
      'real_order_submit_allowed': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    };
    notifyListeners();
    return const ActionResult(
      success: true,
      message:
          'Manual buy ticket prepared. Validate and confirm in Trading before submit.',
    );
  }

  ActionResult prepareKisManualSellFromPosition(PositionSummary position) {
    final symbol = position.symbol.trim();
    final qty = position.qty.floor();
    if (symbol.isEmpty || qty < 1) {
      return const ActionResult(
        success: false,
        message: 'Position is missing a sell symbol or whole-share quantity.',
      );
    }

    selectedOrderMarket = PortfolioMarket.kr;
    orderTicketSymbol = symbol;
    orderTicketSide = 'sell';
    orderTicketQty = qty;
    orderTicketQtyInput = qty.toString();
    orderValidationResult = null;
    orderValidationError = null;
    kisLiveConfirmation = false;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    orderTicketSourceMetadata = {
      'source': 'kis_portfolio_manual_sell',
      'source_type': 'operator_confirmed_position_exit',
      'symbol': symbol,
      if (position.name.isNotEmpty) 'company_name': position.name,
      'suggested_quantity': qty,
      'quantity': qty,
      'current_price': position.currentPrice,
      'cost_basis': position.costBasis,
      'current_value': position.marketValue,
      'unrealized_pl': position.unrealizedPl,
      'unrealized_pl_pct': position.unrealizedPlpc,
      'exit_reason': 'operator_selected_position_exit',
      'trigger_source': 'portfolio_snapshot',
      'trigger_flags': {
        'manual_review_required': true,
      },
      'position_snapshot': {
        'symbol': symbol,
        if (position.name.isNotEmpty) 'company_name': position.name,
        'quantity': qty,
        'current_price': position.currentPrice,
        'cost_basis': position.costBasis,
        'current_value': position.marketValue,
        'unrealized_pl': position.unrealizedPl,
        'unrealized_pl_pct': position.unrealizedPlpc,
      },
      'runtime_safety_snapshot': {
        'dry_run': settings.dryRun,
        'kill_switch': settings.killSwitch,
        'kis_enabled': kisSafetyStatus.kisEnabled,
        'kis_real_order_enabled': kisSafetyStatus.kisRealOrderEnabled,
        'market_open': kisSafetyStatus.marketOpen,
      },
      'manual_confirm_required': true,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
      'real_order_submit_allowed': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    };
    notifyListeners();
    return const ActionResult(
      success: true,
      message:
          'Manual sell ticket prepared from portfolio. Validate and confirm before submit.',
    );
  }

  Future<ActionResult> prepareKisManualSellFromManagedPosition(
    ManagedPosition position,
  ) async {
    final symbol = position.symbol.trim();
    if (symbol.isEmpty) {
      return const ActionResult(
        success: false,
        message: 'Position is missing a sell symbol.',
      );
    }

    try {
      final preparation = await apiClient.prepareKisManualSell(symbol);
      latestManualSellPreparation = preparation;
      final qty = preparation.quantity.floor();
      if (!preparation.canPrepare || qty < 1) {
        notifyListeners();
        return ActionResult(
          success: false,
          message: preparation.blockReasons.isEmpty
              ? 'Manual sell cannot be prepared for this position.'
              : 'Manual sell blocked: ${preparation.blockReasons.join(', ')}',
        );
      }

      selectedOrderMarket = PortfolioMarket.kr;
      orderTicketSymbol = preparation.symbol;
      orderTicketSide = 'sell';
      orderTicketQty = qty;
      orderTicketQtyInput = qty.toString();
      orderValidationResult = null;
      orderValidationError = null;
      kisLiveConfirmation = false;
      kisManualOrderError = null;
      kisManualOrderErrorRaw = null;
      orderTicketSourceMetadata = preparation.sourceMetadata.isNotEmpty
          ? preparation.sourceMetadata
          : {
              'source': 'kis_portfolio_manual_sell',
              'source_type': 'operator_confirmed_position_exit',
              'symbol': preparation.symbol,
              'company_name': preparation.companyName,
              'quantity': qty,
              'suggested_quantity': qty,
              'current_price': preparation.currentPrice,
              'estimated_amount': preparation.estimatedAmount,
              'exit_reason': preparation.exitReason,
              'manual_confirm_required': true,
              'auto_buy_enabled': false,
              'auto_sell_enabled': false,
              'scheduler_real_order_enabled': false,
              'real_order_submit_allowed': false,
              'real_order_submitted': false,
              'broker_submit_called': false,
              'manual_submit_called': false,
            };
      notifyListeners();
      return ActionResult(
        success: true,
        message: preparation.canSubmit
            ? 'Manual sell ticket prepared. Validate and confirm before submit.'
            : 'Manual sell ticket prepared; backend safety may still block submit.',
      );
    } catch (e) {
      final message = _primaryMessage(ApiErrorFormatter.format(e.toString()));
      return ActionResult(success: false, message: message);
    }
  }

  ActionResult prepareKisManualSellFromExitCandidate(
    KisLiveExitCandidate candidate, {
    KisLiveExitPreflightResult? preflight,
  }) {
    final symbol = candidate.symbol.trim();
    final qty = candidate.suggestedQuantityInt;
    if (symbol.isEmpty || qty == null) {
      return const ActionResult(
        success: false,
        message: 'Exit candidate is missing a sell symbol or quantity.',
      );
    }

    selectedOrderMarket = PortfolioMarket.kr;
    orderTicketSymbol = symbol;
    orderTicketSide = 'sell';
    orderTicketQty = qty;
    orderTicketQtyInput = qty.toString();
    orderValidationResult = null;
    orderValidationError = null;
    kisLiveConfirmation = false;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    orderTicketSourceMetadata =
        _exitPreflightSourceMetadata(candidate, preflight: preflight);
    notifyListeners();
    return const ActionResult(
      success: true,
      message:
          'Manual sell ticket prepared. Validate and confirm before submit.',
    );
  }

  ActionResult prepareKisManualSellFromShadowCandidate(
    KisExitShadowCandidate candidate, {
    KisExitShadowDecision? decision,
  }) {
    final symbol = candidate.symbol.trim();
    final qty = candidate.suggestedQuantityInt;
    if (symbol.isEmpty || qty == null) {
      return const ActionResult(
        success: false,
        message: 'Shadow candidate is missing a sell symbol or quantity.',
      );
    }

    selectedOrderMarket = PortfolioMarket.kr;
    orderTicketSymbol = symbol;
    orderTicketSide = 'sell';
    orderTicketQty = qty;
    orderTicketQtyInput = qty.toString();
    orderValidationResult = null;
    orderValidationError = null;
    kisLiveConfirmation = false;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    orderTicketSourceMetadata =
        _exitShadowSourceMetadata(candidate, decision: decision);
    notifyListeners();
    return const ActionResult(
      success: true,
      message:
          'Manual sell ticket prepared from shadow decision. Validate and confirm before submit.',
    );
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

  Future<ActionResult> refreshWatchlist() async {
    watchlistLoading = true;
    watchlistError = null;
    notifyListeners();
    try {
      await loadMarketWatchlists();
      if (watchlistError != null) {
        return ActionResult(success: false, message: watchlistError!);
      }

      try {
        final latestRun = await apiClient.fetchLatestWatchlistRunResult();
        if (latestRun != null) {
          runResult = latestRun;
          hasLatestRunResult = true;
          showingOfflineFallback = false;
        }
      } catch (e) {
        watchlistError = 'Latest watchlist run unavailable: $e';
        return ActionResult(success: false, message: watchlistError!);
      }

      return const ActionResult(success: true, message: 'Watchlist refreshed.');
    } finally {
      watchlistLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> updateKosdaqTop50Watchlist() async {
    if (kosdaqTop50Updating) {
      return const ActionResult(
        success: false,
        message: 'KOSDAQ top 50 watchlist update already in progress.',
      );
    }

    kosdaqTop50Updating = true;
    kosdaqTop50UpdateError = null;
    notifyListeners();
    try {
      final result = await apiClient.updateKosdaqTop50Watchlist();
      latestKosdaqTop50Update = result;
      await loadMarketWatchlists();
      if (watchlistError != null) {
        return ActionResult(success: false, message: watchlistError!);
      }
      return const ActionResult(
        success: true,
        message: 'KOSDAQ top 50 watchlist updated.',
      );
    } catch (e) {
      kosdaqTop50UpdateError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kosdaqTop50UpdateError!),
      );
    } finally {
      kosdaqTop50Updating = false;
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
      marketClosureReason: kisSafetyStatus.marketClosureReason,
      marketClosureName: kisSafetyStatus.marketClosureName,
      effectiveClose: kisSafetyStatus.effectiveClose,
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
    final qty = parsedOrderTicketQty;
    if (symbol.isEmpty || qty == null) {
      orderValidationResult = null;
      orderValidationError = null;
      notifyListeners();
      return const ActionResult(
        success: false,
        message: 'Enter quantity 1 or higher.',
      );
    }
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
        sourceMetadata: orderTicketSourceMetadata,
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
        qty: parsedOrderTicketQty!,
        orderType: 'market',
        confirmLive: kisLiveConfirmation,
        sourceMetadata: orderTicketSourceMetadata,
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
      await _refreshKrPortfolioSummary();
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

  Future<ActionResult> runKisDryRunAuto() async {
    if (kisAutoSimulatorLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS dry-run auto already in progress.',
      );
    }

    kisAutoSimulatorLoading = true;
    kisAutoSimulatorError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisDryRunAuto(
        gateLevel: selectedGateLevel,
      );
      kisAutoSimulatorResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      return ActionResult(
        success: true,
        message: 'KIS dry-run auto completed: ${result.result}.',
      );
    } catch (e) {
      kisAutoSimulatorError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisAutoSimulatorError!),
      );
    } finally {
      kisAutoSimulatorLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisSchedulerStatus({bool silent = false}) async {
    kisSchedulerStatusLoading = true;
    kisSchedulerStatusError = null;
    if (!silent) notifyListeners();
    try {
      kisSchedulerStatus = await apiClient.fetchKisSchedulerStatus();
      kisSchedulerStatusLoaded = true;
      return const ActionResult(
        success: true,
        message: 'KIS scheduler simulation status refreshed.',
      );
    } catch (e) {
      kisSchedulerStatusError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerStatusError!),
      );
    } finally {
      kisSchedulerStatusLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisSchedulerDryRunOnce() async {
    if (kisSchedulerRunLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS scheduler dry-run already in progress.',
      );
    }

    kisSchedulerRunLoading = true;
    kisSchedulerRunError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisSchedulerDryRunOnce();
      kisSchedulerRunResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      await _refreshKisOrdersAfterAction(preferredOrderId: result.orderId);
      await refreshKisSchedulerStatus(silent: true);
      return ActionResult(
        success: true,
        message: 'KIS scheduler dry-run completed: ${result.result}.',
      );
    } catch (e) {
      kisSchedulerRunError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerRunError!),
      );
    } finally {
      kisSchedulerRunLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisSchedulerReadiness({
    bool silent = false,
  }) async {
    if (kisSchedulerReadinessLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS scheduler readiness already in progress.',
      );
    }

    kisSchedulerReadinessLoading = true;
    kisSchedulerReadinessError = null;
    if (!silent) notifyListeners();
    try {
      final result = await apiClient.fetchKisSchedulerReadiness();
      latestKisSchedulerReadiness = result;
      return ActionResult(
        success: true,
        message:
            'KIS scheduler readiness refreshed: ${result.summary.readinessStatus}.',
      );
    } catch (e) {
      kisSchedulerReadinessError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerReadinessError!),
      );
    } finally {
      kisSchedulerReadinessLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisSchedulerDryRunOrchestrationOnce({
    bool silent = false,
  }) async {
    if (kisSchedulerDryRunOrchestrationLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS scheduler dry-run orchestration already in progress.',
      );
    }

    kisSchedulerDryRunOrchestrationLoading = true;
    kisSchedulerDryRunOrchestrationError = null;
    if (!silent) notifyListeners();
    try {
      final result = await apiClient.runKisSchedulerDryRunOrchestrationOnce();
      latestKisSchedulerDryRunOrchestration = result;
      return ActionResult(
        success: true,
        message:
            'KIS scheduler dry-run orchestration completed: ${result.result}.',
      );
    } catch (e) {
      kisSchedulerDryRunOrchestrationError =
          ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerDryRunOrchestrationError!),
      );
    } finally {
      kisSchedulerDryRunOrchestrationLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisSchedulerDryRunReview({
    bool silent = false,
  }) async {
    if (kisSchedulerDryRunReviewLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS scheduler dry-run review already in progress.',
      );
    }

    kisSchedulerDryRunReviewLoading = true;
    kisSchedulerDryRunReviewError = null;
    if (!silent) notifyListeners();
    try {
      final result = await apiClient.fetchKisSchedulerDryRunReview();
      latestKisSchedulerDryRunReview = result;
      return ActionResult(
        success: true,
        message:
            'KIS scheduler dry-run review refreshed: ${result.summary.totalRuns} runs.',
      );
    } catch (e) {
      kisSchedulerDryRunReviewError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerDryRunReviewError!),
      );
    } finally {
      kisSchedulerDryRunReviewLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisAutoReadiness({bool silent = false}) async {
    if (kisAutoReadinessLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS auto readiness refresh already in progress.',
      );
    }

    kisAutoReadinessLoading = true;
    kisAutoReadinessError = null;
    if (!silent) notifyListeners();
    try {
      final result = await apiClient.fetchKisAutoReadiness();
      kisAutoReadinessResult = result;
      kisAutoReadinessLoaded = true;
      return const ActionResult(
        success: true,
        message: 'KIS auto readiness refreshed.',
      );
    } catch (e) {
      kisAutoReadinessError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisAutoReadinessError!),
      );
    } finally {
      kisAutoReadinessLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisAutoPreflightOnce() async {
    if (kisAutoPreflightLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS auto preflight already in progress.',
      );
    }

    kisAutoPreflightLoading = true;
    kisAutoReadinessError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisAutoPreflightOnce();
      kisAutoReadinessResult = result;
      kisAutoReadinessLoaded = true;
      return ActionResult(
        success: true,
        message: 'KIS auto preflight completed: ${result.reason}.',
      );
    } catch (e) {
      kisAutoReadinessError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisAutoReadinessError!),
      );
    } finally {
      kisAutoPreflightLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisLiveExitPreflight() async {
    if (kisLiveExitPreflightLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS live exit preflight already in progress.',
      );
    }

    kisLiveExitPreflightLoading = true;
    kisLiveExitPreflightError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisLiveExitPreflight();
      kisLiveExitPreflightResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      return ActionResult(
        success: true,
        message: 'KIS live exit preflight completed: ${result.action}.',
      );
    } catch (e) {
      kisLiveExitPreflightError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisLiveExitPreflightError!),
      );
    } finally {
      kisLiveExitPreflightLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisExitShadowOnce() async {
    if (kisExitShadowLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS exit shadow decision already in progress.',
      );
    }

    kisExitShadowLoading = true;
    kisExitShadowError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisExitShadowOnce();
      latestKisExitShadowDecision = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      return ActionResult(
        success: true,
        message: 'KIS exit shadow decision completed: ${result.decision}.',
      );
    } catch (e) {
      kisExitShadowError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisExitShadowError!),
      );
    } finally {
      kisExitShadowLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisShadowExitReview() async {
    if (kisShadowExitReviewLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS shadow exit review already in progress.',
      );
    }

    kisShadowExitReviewLoading = true;
    kisShadowExitReviewError = null;
    notifyListeners();
    try {
      latestKisShadowExitReview =
          await apiClient.fetchKisShadowExitReview(days: 30, limit: 20);
      return const ActionResult(
        success: true,
        message: 'KIS shadow exit review refreshed.',
      );
    } catch (e) {
      kisShadowExitReviewError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisShadowExitReviewError!),
      );
    } finally {
      kisShadowExitReviewLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisShadowExitReviewQueue() async {
    if (kisShadowExitReviewQueueLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS shadow exit review queue already in progress.',
      );
    }

    kisShadowExitReviewQueueLoading = true;
    kisShadowExitReviewQueueError = null;
    notifyListeners();
    try {
      latestKisShadowExitReviewQueue =
          await apiClient.fetchKisShadowExitReviewQueue(days: 30, limit: 50);
      return const ActionResult(
        success: true,
        message: 'KIS shadow exit review queue refreshed.',
      );
    } catch (e) {
      kisShadowExitReviewQueueError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisShadowExitReviewQueueError!),
      );
    } finally {
      kisShadowExitReviewQueueLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> markKisShadowExitQueueItemReviewed(
    String queueId, {
    String? note,
  }) async {
    if (kisShadowExitReviewQueueLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS shadow exit review queue already in progress.',
      );
    }

    kisShadowExitReviewQueueLoading = true;
    kisShadowExitReviewQueueError = null;
    notifyListeners();
    try {
      await apiClient.markKisShadowExitQueueItemReviewed(queueId, note: note);
      latestKisShadowExitReviewQueue =
          await apiClient.fetchKisShadowExitReviewQueue(days: 30, limit: 50);
      return const ActionResult(
        success: true,
        message: 'KIS shadow exit queue item marked reviewed.',
      );
    } catch (e) {
      kisShadowExitReviewQueueError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisShadowExitReviewQueueError!),
      );
    } finally {
      kisShadowExitReviewQueueLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> dismissKisShadowExitQueueItem(
    String queueId, {
    String? note,
  }) async {
    if (kisShadowExitReviewQueueLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS shadow exit review queue already in progress.',
      );
    }

    kisShadowExitReviewQueueLoading = true;
    kisShadowExitReviewQueueError = null;
    notifyListeners();
    try {
      await apiClient.dismissKisShadowExitQueueItem(queueId, note: note);
      latestKisShadowExitReviewQueue =
          await apiClient.fetchKisShadowExitReviewQueue(days: 30, limit: 50);
      return const ActionResult(
        success: true,
        message: 'KIS shadow exit queue item dismissed.',
      );
    } catch (e) {
      kisShadowExitReviewQueueError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisShadowExitReviewQueueError!),
      );
    } finally {
      kisShadowExitReviewQueueLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisLimitedAutoSellOnce() async {
    if (kisLimitedAutoSellLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS limited auto sell already in progress.',
      );
    }

    kisLimitedAutoSellLoading = true;
    kisLimitedAutoSellError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisLimitedAutoSellOnce();
      latestKisLimitedAutoSellResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      return ActionResult(
        success: true,
        message: 'KIS limited auto sell completed: ${result.reason}.',
      );
    } catch (e) {
      kisLimitedAutoSellError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisLimitedAutoSellError!),
      );
    } finally {
      kisLimitedAutoSellLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisLimitedAutoSellStatus() async {
    if (kisLimitedAutoSellLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS limited auto sell already in progress.',
      );
    }

    kisLimitedAutoSellLoading = true;
    kisLimitedAutoSellError = null;
    notifyListeners();
    try {
      final result = await apiClient.fetchKisLimitedAutoSellStatus();
      latestKisLimitedAutoSellResult = result;
      return ActionResult(
        success: true,
        message: 'KIS limited auto sell status refreshed: ${result.reason}.',
      );
    } catch (e) {
      kisLimitedAutoSellError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisLimitedAutoSellError!),
      );
    } finally {
      kisLimitedAutoSellLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisLimitedAutoSellPreflightOnce() async {
    if (kisLimitedAutoSellLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS limited auto sell already in progress.',
      );
    }

    kisLimitedAutoSellLoading = true;
    kisLimitedAutoSellError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisLimitedAutoSellPreflightOnce();
      latestKisLimitedAutoSellResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      return ActionResult(
        success: true,
        message: 'KIS stop-loss preflight completed: ${result.reason}.',
      );
    } catch (e) {
      kisLimitedAutoSellError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisLimitedAutoSellError!),
      );
    } finally {
      kisLimitedAutoSellLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisBuyShadowOnce() async {
    if (kisBuyShadowLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS buy shadow decision already in progress.',
      );
    }

    kisBuyShadowLoading = true;
    kisBuyShadowError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisBuyShadowOnce();
      latestKisBuyShadowDecision = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      return ActionResult(
        success: true,
        message:
            'KIS buy shadow decision completed: ${result.decision} (${result.reason}).',
      );
    } catch (e) {
      kisBuyShadowError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisBuyShadowError!),
      );
    } finally {
      kisBuyShadowLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisGuardedCheck() {
    return runKisBuyShadowOnce();
  }

  Future<ActionResult> refreshKisLimitedAutoBuyStatus({
    int? gateLevel,
  }) async {
    if (kisLimitedAutoBuyLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS limited auto buy already in progress.',
      );
    }

    kisLimitedAutoBuyLoading = true;
    kisLimitedAutoBuyError = null;
    notifyListeners();
    try {
      final result = await apiClient.fetchKisLimitedAutoBuyStatus(
        gateLevel: gateLevel,
      );
      latestKisLimitedAutoBuyResult = result;
      return ActionResult(
        success: true,
        message: 'KIS buy readiness status: ${result.reason}.',
      );
    } catch (e) {
      kisLimitedAutoBuyError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisLimitedAutoBuyError!),
      );
    } finally {
      kisLimitedAutoBuyLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisLimitedAutoBuyPreflightOnce({
    int? gateLevel,
  }) async {
    if (kisLimitedAutoBuyLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS limited auto buy already in progress.',
      );
    }

    kisLimitedAutoBuyLoading = true;
    kisLimitedAutoBuyError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisLimitedAutoBuyPreflightOnce(
        gateLevel: gateLevel,
      );
      latestKisLimitedAutoBuyResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      return ActionResult(
        success: true,
        message: 'KIS buy preflight completed: ${result.reason}.',
      );
    } catch (e) {
      kisLimitedAutoBuyError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisLimitedAutoBuyError!),
      );
    } finally {
      kisLimitedAutoBuyLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisLimitedAutoBuyOnce({int? gateLevel}) async {
    if (kisLimitedAutoBuyLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS limited auto buy already in progress.',
      );
    }

    kisLimitedAutoBuyLoading = true;
    kisLimitedAutoBuyError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisLimitedAutoBuyOnce(
        gateLevel: gateLevel,
      );
      latestKisLimitedAutoBuyResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      return ActionResult(
        success: true,
        message: 'KIS limited buy readiness completed: ${result.reason}.',
      );
    } catch (e) {
      kisLimitedAutoBuyError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisLimitedAutoBuyError!),
      );
    } finally {
      kisLimitedAutoBuyLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisLimitedAutoBuyReview({
    int limit = 20,
    int days = 30,
    String? symbol,
  }) async {
    if (kisLimitedAutoBuyReviewLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS limited buy review already in progress.',
      );
    }

    kisLimitedAutoBuyReviewLoading = true;
    kisLimitedAutoBuyReviewError = null;
    notifyListeners();
    try {
      final result = await apiClient.fetchKisLimitedAutoBuyReview(
        limit: limit,
        days: days,
        symbol: symbol,
      );
      latestKisLimitedAutoBuyReview = result;
      return ActionResult(
        success: true,
        message:
            'KIS limited buy review refreshed: ${result.summary.totalRuns} runs.',
      );
    } catch (e) {
      kisLimitedAutoBuyReviewError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisLimitedAutoBuyReviewError!),
      );
    } finally {
      kisLimitedAutoBuyReviewLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisLimitedAutoBuyExecutionReview({
    int limit = 20,
    int days = 30,
    String? symbol,
  }) async {
    if (kisLimitedAutoBuyExecutionReviewLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS limited buy execution review already in progress.',
      );
    }

    kisLimitedAutoBuyExecutionReviewLoading = true;
    kisLimitedAutoBuyExecutionReviewError = null;
    notifyListeners();
    try {
      final result = await apiClient.fetchKisLimitedAutoBuyExecutionReview(
        limit: limit,
        days: days,
        symbol: symbol,
      );
      latestKisLimitedAutoBuyExecutionReview = result;
      return ActionResult(
        success: true,
        message:
            'KIS limited buy execution review refreshed: ${result.summary.submittedBuyCount} submitted, ${result.summary.blockedCount} blocked.',
      );
    } catch (e) {
      kisLimitedAutoBuyExecutionReviewError =
          ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisLimitedAutoBuyExecutionReviewError!),
      );
    } finally {
      kisLimitedAutoBuyExecutionReviewLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisAnalyzeAndBuySelectedSymbol({
    required String symbol,
    required int quantity,
    required int gateLevel,
    bool confirmLive = true,
  }) async {
    return runKisSingleSymbolAnalyzeBuy(
      symbol: symbol,
      quantity: quantity,
      gateLevel: gateLevel,
      confirmLive: confirmLive,
    );
  }

  Future<ActionResult> runKisSingleSymbolAnalyzeBuy({
    required String symbol,
    required int quantity,
    required int gateLevel,
    required bool confirmLive,
  }) async {
    if (kisSingleSymbolTradingLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS Analyze & Buy already in progress.',
      );
    }

    final normalizedSymbol = symbol.trim().toUpperCase();
    kisSingleSymbolTradingLoading = true;
    kisSingleSymbolTradingError = null;
    latestKisSingleSymbolTradingResult = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisSingleSymbolAnalyzeBuy(
        symbol: normalizedSymbol,
        gateLevel: gateLevel,
        quantity: quantity,
        confirmLive: confirmLive,
      );
      latestKisSingleSymbolTradingResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      await _refreshPortfolioSummaries();
      if (result.realOrderSubmitted || result.orderId != null) {
        await refreshKisOrderMonitoring(silent: true);
      }
      final resultText =
          result.result.trim().isEmpty ? 'blocked' : result.result.trim();
      return ActionResult(
        success: true,
        message: 'KIS Analyze & Buy completed: $resultText.',
      );
    } catch (e) {
      kisSingleSymbolTradingError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSingleSymbolTradingError!),
      );
    } finally {
      kisSingleSymbolTradingLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisGuardedTradingOnce() async {
    await refreshKisSafetyStatus(silent: true);

    if (!canRunKisGuardedTradingOnce) {
      return ActionResult(
        success: false,
        message: kisGuardedRunBlockedMessage(),
      );
    }

    final result = await runKisLimitedAutoBuyOnce(
      gateLevel: selectedGateLevel,
    );
    if (result.success) {
      kisGuardedRunConfirmation = false;
      notifyListeners();
    }
    return result;
  }

  Future<ActionResult> runKisSchedulerLiveOnce() async {
    if (kisSchedulerLiveLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS scheduler live run already in progress.',
      );
    }

    kisSchedulerLiveLoading = true;
    kisSchedulerLiveError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisSchedulerLiveOnce();
      latestKisSchedulerLiveResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      await refreshKisSchedulerStatus(silent: true);
      return ActionResult(
        success: true,
        message: 'KIS scheduler live run completed: ${result.reason}.',
      );
    } catch (e) {
      kisSchedulerLiveError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerLiveError!),
      );
    } finally {
      kisSchedulerLiveLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisSchedulerGuardedSellStatus() async {
    if (kisSchedulerGuardedSellLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS scheduler guarded sell already in progress.',
      );
    }

    kisSchedulerGuardedSellLoading = true;
    kisSchedulerGuardedSellError = null;
    notifyListeners();
    try {
      final result = await apiClient.fetchKisSchedulerGuardedSellStatus();
      latestKisSchedulerGuardedSellResult = result;
      return ActionResult(
        success: true,
        message:
            'KIS scheduler guarded sell status refreshed: ${result.reason}.',
      );
    } catch (e) {
      kisSchedulerGuardedSellError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerGuardedSellError!),
      );
    } finally {
      kisSchedulerGuardedSellLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisSchedulerGuardedSellOnce() async {
    if (kisSchedulerGuardedSellLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS scheduler guarded sell already in progress.',
      );
    }

    kisSchedulerGuardedSellLoading = true;
    kisSchedulerGuardedSellError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisSchedulerGuardedSellOnce();
      latestKisSchedulerGuardedSellResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      await refreshKisSchedulerStatus(silent: true);
      if (result.realOrderSubmitted || result.orderId != null) {
        await refreshKisOrderMonitoring(silent: true);
      }
      return ActionResult(
        success: true,
        message: 'KIS scheduler guarded sell completed: ${result.reason}.',
      );
    } catch (e) {
      kisSchedulerGuardedSellError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerGuardedSellError!),
      );
    } finally {
      kisSchedulerGuardedSellLoading = false;
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
      await _refreshKisManagedPositions();
    } catch (_) {
      krPortfolioSummary = PortfolioSummary.empty(currency: 'KRW');
      kisManagedPositions = const [];
      krPortfolioUnavailable = true;
      krPortfolioError = 'KIS account data unavailable';
    }
  }

  Future<void> _refreshKisManagedPositions() async {
    kisManagedPositionsLoading = true;
    kisManagedPositionsError = null;
    try {
      kisManagedPositions = await apiClient.fetchKisManagedPositions();
    } catch (e) {
      kisManagedPositions = const [];
      kisManagedPositionsError =
          'KIS position management unavailable: ${ApiErrorFormatter.format(e.toString())}';
    } finally {
      kisManagedPositionsLoading = false;
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
    final currentQty = parsedOrderTicketQty;
    final qtyMatches = currentQty != null && validation.qty == currentQty;
    final sideMatches = validation.side == orderTicketSide;
    if (!symbolMatches || !qtyMatches || !sideMatches) {
      return 'Current order input changed after validation. Validate again.';
    }

    if (!kisLiveConfirmation) return 'Confirm live KIS order first.';
    if (kisSafetyStatus.runtimeDryRun) {
      return 'Live submit blocked: dry-run is ON';
    }
    if (kisSafetyStatus.killSwitch) {
      return 'Live submit blocked: kill switch is ON';
    }
    if (!kisSafetyStatus.kisEnabled) {
      return 'Live submit blocked: KIS trading disabled';
    }
    if (!kisSafetyStatus.kisRealOrderEnabled) {
      return 'Live submit blocked: KIS real orders disabled';
    }
    if (!kisSafetyStatus.marketOpen) return _marketClosedMessage();
    if (currentOrderRequiresEntryWindow && !kisSafetyStatus.entryAllowedNow) {
      return _entryBlockedMessage();
    }
    if (!isOrderTicketInputValid) return 'Enter a valid symbol and quantity.';
    return 'Live KIS submit is blocked by the checklist.';
  }

  String kisRuntimeLiveSubmitMessage() {
    if (kisCurrentOrderRuntimeGatesOpen) {
      return 'Live submit available after validation + confirmation';
    }
    return kisSubmitBlockedMessageForRuntimeStatus(forCurrentOrder: true);
  }

  String kisGuardedRunBlockedMessage() {
    if (kisGuardedRunSymbol.trim().isEmpty) {
      return 'Enter a KIS symbol before running guarded trading.';
    }
    if (!kisRuntimeLiveSubmitGatesOpen) {
      return kisSubmitBlockedMessageForRuntimeStatus();
    }
    if (!kisGuardedRunConfirmation) {
      return 'Confirm live KIS guarded run first.';
    }
    return 'KIS guarded run is blocked by the checklist.';
  }

  String kisSubmitBlockedMessageForRuntimeStatus(
      {bool forCurrentOrder = false}) {
    if (kisSafetyStatus.runtimeDryRun) {
      return 'Live submit blocked: dry-run is ON';
    }
    if (kisSafetyStatus.killSwitch) {
      return 'Live submit blocked: kill switch is ON';
    }
    if (!kisSafetyStatus.kisEnabled) {
      return 'Live submit blocked: KIS trading disabled';
    }
    if (!kisSafetyStatus.kisRealOrderEnabled) {
      return 'Live submit blocked: KIS real orders disabled';
    }
    if (!kisSafetyStatus.marketOpen) return _marketClosedMessage();
    final requiresEntryWindow =
        forCurrentOrder ? currentOrderRequiresEntryWindow : true;
    if (requiresEntryWindow && !kisSafetyStatus.entryAllowedNow) {
      return _entryBlockedMessage();
    }
    return 'Live submit blocked: runtime safety status unavailable';
  }

  String _marketClosedMessage() {
    final reason = kisSafetyStatus.marketClosureName ??
        kisSafetyStatus.marketClosureReason;
    if (reason != null && reason.isNotEmpty) {
      return 'Live submit blocked: market is closed ($reason)';
    }
    final close = kisSafetyStatus.effectiveClose;
    if (close != null && close.isNotEmpty) {
      return 'Live submit blocked: market is closed (effective_close $close)';
    }
    return 'Live submit blocked: market is closed';
  }

  String _entryBlockedMessage() {
    final cutoff = kisSafetyStatus.noNewEntryAfter;
    if (cutoff.isNotEmpty) {
      return 'Live submit blocked: entry not allowed now (no_new_entry_after $cutoff)';
    }
    return 'Live submit blocked: entry not allowed now';
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

  void _clearOrderTicketSourceMetadata() {
    orderTicketSourceMetadata = null;
    orderValidationResult = null;
    orderValidationError = null;
    kisLiveConfirmation = false;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
  }
}

int? _parseOrderTicketQty(String value) {
  final trimmed = value.trim();
  if (trimmed.isEmpty || !RegExp(r'^\d+$').hasMatch(trimmed)) return null;
  final parsed = int.tryParse(trimmed);
  if (parsed == null || parsed < 1) return null;
  return parsed;
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

bool _signalMatchesId(Map<String, dynamic> signal, String expectedSignalId) {
  final normalizedExpected = expectedSignalId.trim();
  final candidates = [
    signal['id'],
    signal['signal_id'],
    if (signal['signal'] is Map) (signal['signal'] as Map)['id'],
    if (signal['signal'] is Map) (signal['signal'] as Map)['signal_id'],
  ];

  for (final candidate in candidates) {
    if (candidate?.toString().trim() == normalizedExpected) return true;
  }
  return false;
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

Map<String, dynamic> _exitPreflightSourceMetadata(
  KisLiveExitCandidate candidate, {
  KisLiveExitPreflightResult? preflight,
}) {
  final checkedAt = preflight?.checkedAt ?? preflight?.createdAt;
  final suggestedQuantity =
      candidate.suggestedQuantity ?? candidate.quantityAvailable;
  return {
    'source': 'kis_live_exit_preflight',
    'source_type': 'manual_confirm_exit',
    if (checkedAt != null) 'preflight_checked_at': checkedAt,
    if (preflight?.runKey != null) 'preflight_run_key': preflight!.runKey,
    if (preflight?.runId != null) 'preflight_id': preflight!.runId,
    'exit_trigger': candidate.trigger,
    'trigger_source': candidate.triggerSource,
    if (candidate.unrealizedPl != null) 'unrealized_pl': candidate.unrealizedPl,
    if (candidate.unrealizedPlPct != null)
      'unrealized_pl_pct': candidate.unrealizedPlPct,
    if (candidate.costBasis != null) 'cost_basis': candidate.costBasis,
    if (candidate.currentValue != null) 'current_value': candidate.currentValue,
    if (candidate.currentPrice != null) 'current_price': candidate.currentPrice,
    if (suggestedQuantity != null) 'suggested_quantity': suggestedQuantity,
    'risk_flags': candidate.riskFlags,
    'gating_notes': candidate.gatingNotes,
    'manual_confirm_required': true,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'real_order_submit_allowed': false,
    'preflight_real_order_submitted': false,
    'preflight_broker_submit_called': false,
    'preflight_manual_submit_called': false,
  };
}

Map<String, dynamic> _exitShadowSourceMetadata(
  KisExitShadowCandidate candidate, {
  KisExitShadowDecision? decision,
}) {
  final checkedAt = decision?.checkedAt ?? decision?.createdAt;
  final suggestedQuantity =
      candidate.suggestedQuantity ?? candidate.quantityAvailable;
  return {
    'source': 'kis_exit_shadow_decision',
    'source_type': 'dry_run_sell_simulation',
    if (checkedAt != null) 'shadow_decision_checked_at': checkedAt,
    if (decision?.runKey != null) 'shadow_decision_run_key': decision!.runKey,
    'exit_trigger': candidate.trigger,
    'trigger_source': candidate.triggerSource,
    if (candidate.unrealizedPl != null) 'unrealized_pl': candidate.unrealizedPl,
    if (candidate.unrealizedPlPct != null)
      'unrealized_pl_pct': candidate.unrealizedPlPct,
    if (candidate.costBasis != null) 'cost_basis': candidate.costBasis,
    if (candidate.currentValue != null) 'current_value': candidate.currentValue,
    if (candidate.currentPrice != null) 'current_price': candidate.currentPrice,
    if (suggestedQuantity != null) 'suggested_quantity': suggestedQuantity,
    'risk_flags': candidate.riskFlags,
    'gating_notes': candidate.gatingNotes,
    'manual_confirm_required': true,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'real_order_submit_allowed': false,
    'shadow_real_order_submitted': false,
    'shadow_broker_submit_called': false,
    'shadow_manual_submit_called': false,
  };
}
