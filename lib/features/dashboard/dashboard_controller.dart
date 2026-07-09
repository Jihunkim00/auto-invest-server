import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/i18n/app_language.dart';
import '../../core/i18n/app_strings.dart';
import '../../core/network/api_client.dart';
import '../../core/network/api_error_formatter.dart';
import '../../core/utils/kr_symbol.dart';
import '../../models/agent_chat_conversation.dart';
import '../../models/agent_chat_live_order_action.dart';
import '../../models/agent_chat_live_order_readiness.dart';
import '../../models/agent_chat_message.dart';
import '../../models/agent_chat_send_response.dart';
import '../../models/agent_chat_strategy_action.dart';
import '../../models/agent_command.dart';
import '../../models/agent_live_prefill.dart';
import '../../models/agent_operations.dart';
import '../../models/agent_plan.dart';
import '../../models/agent_review_queue.dart';
import '../../models/agent_run.dart';
import '../../models/automation_runtime_monitor.dart';
import '../../models/auto_buy_live_phase1.dart';
import '../../models/auto_exit_candidate.dart';
import '../../models/auto_sell_live_phase1.dart';
import '../../models/candidate.dart';
import '../../models/daily_ops_summary.dart';
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
import '../../models/kis_scheduler_guarded_buy.dart';
import '../../models/kis_scheduler_guarded_sell_review.dart';
import '../../models/kis_scheduler_readiness.dart';
import '../../models/kis_scheduler_simulation.dart';
import '../../models/kis_scheduler_live.dart';
import '../../models/log_items.dart';
import '../../models/market_watchlist.dart';
import '../../models/managed_position.dart';
import '../../models/manual_trading_run_result.dart';
import '../../models/ops_settings.dart';
import '../../models/ops_production_readiness.dart';
import '../../models/order_validation_result.dart';
import '../../models/operator_alerts.dart';
import '../../models/portfolio_summary.dart';
import '../../models/position_exit_review.dart';
import '../../models/position_lifecycle.dart';
import '../../models/position_management_dry_run.dart';
import '../../models/scheduler_status.dart';
import '../../models/strategy_profile.dart';
import '../../models/strategy_auto_buy_operations.dart';
import '../../models/strategy_auto_buy_promotion.dart';
import '../../models/strategy_auto_buy_scheduler.dart';
import '../../models/strategy_performance.dart';
import '../../models/strategy_risk.dart';
import '../../models/strategy_dry_run_auto_buy.dart';
import '../../models/strategy_live_auto_buy.dart';
import '../../models/strategy_live_auto_exit.dart';
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
  DashboardController(
    this.apiClient, {
    bool autoload = true,
    AppLanguage initialLanguage = AppLanguage.korean,
  }) : appLanguage = initialLanguage {
    agentMessages = _defaultAgentSafetyMessages(appLanguage);
    if (autoload) {
      load();
    }
  }

  final ApiClient apiClient;
  AppLanguage appLanguage;

  AppStrings get strings => AppStrings(appLanguage);

  void setAppLanguage(AppLanguage language) {
    if (appLanguage == language) return;
    appLanguage = language;
    if (_containsOnlyDefaultAgentSafetyMessage(agentMessages)) {
      agentMessages = _defaultAgentSafetyMessages(appLanguage);
    }
    notifyListeners();
  }

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
  bool schedulerStatusLoading = false;
  bool schedulerStatusLoaded = false;
  String? schedulerStatusError;
  AutomationRuntimeMonitor? automationRuntimeMonitor;
  bool automationRuntimeMonitorLoading = false;
  String? automationRuntimeMonitorError;
  List<TradingLogItem> automationRecentRuns = const [];
  List<OrderLogItem> automationRecentOrders = const [];
  List<SignalLogItem> automationRecentSignals = const [];
  List<AutomationEvent> localAutomationEvents = const [];
  List<PortfolioPositionManagementItem> portfolioManagementItems = const [];
  bool portfolioManagementLoading = false;
  String? portfolioManagementError;
  String? latestSettingsChangeSummary;
  bool opsProductionReadinessLoading = false;
  OpsProductionReadiness? latestOpsProductionReadiness;
  String? opsProductionReadinessError;

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
  Map<String, dynamic>? kisTradingSourceContext;
  bool kisSchedulerLiveLoading = false;
  KisSchedulerLiveResult? latestKisSchedulerLiveResult;
  String? kisSchedulerLiveError;
  bool kisSchedulerGuardedSellLoading = false;
  KisSchedulerGuardedSellResult? latestKisSchedulerGuardedSellResult;
  String? kisSchedulerGuardedSellError;
  bool kisSchedulerGuardedBuyLoading = false;
  KisSchedulerGuardedBuyResult? latestKisSchedulerGuardedBuyResult;
  String? kisSchedulerGuardedBuyError;
  bool kisSchedulerGuardedSellReviewLoading = false;
  KisSchedulerGuardedSellReview? latestKisSchedulerGuardedSellReview;
  String? kisSchedulerGuardedSellReviewError;
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
  AgentChatPanelMode agentChatMode = AgentChatPanelMode.mini;
  List<AgentChatMessage> agentMessages = const [];
  bool isAgentParsing = false;
  bool isAgentPlanCreating = false;
  bool isAgentRunning = false;
  bool isAgentPreparingTicket = false;
  final Set<int> _agentLiveOrderActionBusy = <int>{};
  final Set<int> _agentStrategyActionBusy = <int>{};
  AgentCommandParseResult? latestAgentCommand;
  AgentPlan? latestAgentPlan;
  AgentPlanRunResult? latestAgentRun;
  AgentLivePrefill? latestAgentPrefill;
  String? agentErrorMessage;
  String? activeAgentConversationKey;
  List<AgentChatConversation> agentConversations = const [];
  bool isLoadingAgentHistory = false;
  bool isSavingAgentMessage = false;
  String? agentHistoryError;
  AgentOperationsSnapshot? agentOperationsSnapshot;
  AgentReviewQueue agentReviewQueue = AgentReviewQueue.empty;
  String selectedAgentQueueFilter = 'all';
  bool isLoadingAgentOperations = false;
  bool isLoadingAgentReviewQueue = false;
  String? agentOperationsError;
  AgentChatLiveOrderReadiness? agentChatLiveOrderReadiness;
  bool isLoadingAgentChatLiveOrderReadiness = false;
  String? agentChatLiveOrderSettingsError;
  String? applyingAgentChatLiveOrderPreset;
  List<StrategyProfile> strategyProfiles = const [];
  StrategyProfile? activeStrategyProfile;
  bool strategyProfilesLoading = false;
  String? strategyProfileError;
  String? applyingStrategyProfileName;
  StrategyDailyPerformance? strategyDailyPerformance;
  StrategyMonthlyPerformance? strategyMonthlyPerformance;
  StrategyTradePerformanceList? strategyTradePerformance;
  bool strategyPerformanceLoading = false;
  String? strategyPerformanceError;
  StrategyRiskState? strategyRiskState;
  bool strategyRiskLoading = false;
  String? strategyRiskError;
  StrategyDryRunAutoBuyResult? strategyDryRunAutoBuyResult;
  List<StrategyDryRunAutoBuyResult> strategyDryRunAutoBuyRecent = const [];
  bool strategyDryRunAutoBuyLoading = false;
  String? strategyDryRunAutoBuyError;
  StrategyAutoBuyOperationsStatus? strategyAutoBuyOperationsStatus;
  bool strategyAutoBuyOperationsLoading = false;
  String? strategyAutoBuyOperationsError;
  DailyOpsSummary? dailyOpsSummary;
  bool dailyOpsSummaryLoading = false;
  String? dailyOpsSummaryError;
  OperatorAlerts? operatorAlerts;
  bool operatorAlertsLoading = false;
  String? operatorAlertsError;
  StrategyAutoBuySchedulerStatus? strategyAutoBuySchedulerStatus;
  StrategyAutoBuySchedulerRunResult? strategyAutoBuySchedulerRunResult;
  bool strategyAutoBuySchedulerLoading = false;
  String? strategyAutoBuySchedulerError;
  AutoBuyLivePhase1Result? autoBuyLivePhase1Status;
  AutoBuyLivePhase1Result? autoBuyLivePhase1Result;
  bool autoBuyLivePhase1Loading = false;
  String? autoBuyLivePhase1Error;
  AutoSellLivePhase1Result? autoSellLivePhase1Status;
  AutoSellLivePhase1Result? autoSellLivePhase1Result;
  bool autoSellLivePhase1Loading = false;
  String? autoSellLivePhase1Error;
  List<StrategyAutoBuyPromotion> strategyAutoBuyPromotions = const [];
  bool strategyAutoBuyPromotionsLoading = false;
  String? strategyAutoBuyPromotionsError;
  StrategyLiveAutoBuyReadiness? strategyLiveAutoBuyReadiness;
  StrategyLiveAutoBuyRunResult? strategyLiveAutoBuyResult;
  StrategyLiveAutoBuyResult? latestStrategyLiveAutoBuyConversionResult;
  Map<int, StrategyLiveAutoBuyPreflightResult> strategyLiveAutoBuyPreflights =
      const {};
  List<StrategyLiveAutoBuyRunResult> strategyLiveAutoBuyRecent = const [];
  bool strategyLiveAutoBuyPreflightLoading = false;
  String? strategyLiveAutoBuyPreflightError;
  bool strategyLiveAutoBuyResultLoading = false;
  String? strategyLiveAutoBuyResultError;
  bool strategyLiveAutoBuyLoading = false;
  String? strategyLiveAutoBuyError;
  StrategyLiveAutoExitReadiness? strategyLiveAutoExitReadiness;
  StrategyLiveAutoExitRunResult? strategyLiveAutoExitResult;
  List<StrategyLiveAutoExitRunResult> strategyLiveAutoExitRecent = const [];
  bool strategyLiveAutoExitLoading = false;
  String? strategyLiveAutoExitError;
  AutoExitCandidates? autoExitCandidates;
  bool autoExitCandidatesLoading = false;
  String? autoExitCandidatesError;
  PositionManagementDryRun? positionManagementDryRun;
  bool positionManagementDryRunLoading = false;
  String? positionManagementDryRunError;
  PositionExitReview? positionExitReview;
  PositionSellPreflightResult? latestPositionSellPreflight;
  GuardedPositionSellResult? latestGuardedPositionSellResult;
  PositionLifecycle? positionLifecycle;
  bool positionExitReviewLoading = false;
  String? positionExitReviewError;
  bool positionSellPreflightLoading = false;
  String? positionSellPreflightError;
  bool guardedPositionSellLoading = false;
  String? guardedPositionSellError;
  bool positionLifecycleLoading = false;
  String? positionLifecycleError;
  final String agentConversationId =
      'flutter-agent-${DateTime.now().millisecondsSinceEpoch}';

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

  bool get hasPreparedKisManualSellTicket =>
      selectedOrderMarket == PortfolioMarket.kr &&
      orderTicketSide == 'sell' &&
      orderTicketSourceMetadata != null;

  bool get currentOrderRequiresEntryWindow => orderTicketSide != 'sell';

  bool get kisCurrentOrderRuntimeGatesOpen {
    return !kisSafetyStatus.runtimeDryRun &&
        !kisSafetyStatus.killSwitch &&
        kisSafetyStatus.kisEnabled &&
        kisSafetyStatus.kisRealOrderEnabled &&
        kisSafetyStatus.marketOpen &&
        (!currentOrderRequiresEntryWindow || kisSafetyStatus.entryAllowedNow);
  }

  bool get orderValidationMatchesCurrent {
    final validation = orderValidationResult;
    if (validation == null) return false;

    final symbolMatches = validation.symbol == orderTicketSymbol.trim();
    final currentQty = parsedOrderTicketQty;
    final qtyMatches = currentQty != null && validation.qty == currentQty;
    final sideMatches = validation.side == orderTicketSide;
    return symbolMatches && qtyMatches && sideMatches;
  }

  bool get orderValidationExpired =>
      orderValidationResult?.isValidationExpired == true;

  bool get canSubmitLiveKisOrder {
    final validation = orderValidationResult;
    if (validation == null) return false;

    return !kisManualSubmitLoading &&
        !orderValidationExpired &&
        validation.effectiveSubmitAllowed &&
        validation.validatedForSubmission &&
        isOrderTicketInputValid &&
        orderValidationMatchesCurrent &&
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

  String get selectedBrokerLabel =>
      isKisSelected ? strings.kisBrokerMarket : strings.alpacaBrokerMarket;

  bool isAgentLiveOrderActionBusy(int actionId) =>
      _agentLiveOrderActionBusy.contains(actionId);

  bool isAgentStrategyActionBusy(int actionId) =>
      _agentStrategyActionBusy.contains(actionId);

  StrategyLiveAutoBuyPreflightResult? strategyLiveAutoBuyPreflightForPromotion(
          int promotionId) =>
      strategyLiveAutoBuyPreflights[promotionId];

  StrategyLiveAutoBuyResult? strategyLiveAutoBuyResultForPromotion(
    int promotionId,
  ) {
    final result = latestStrategyLiveAutoBuyConversionResult;
    if (result == null) return null;
    return result.matchesPromotion(promotionId) ? result : null;
  }

  PortfolioSummary get portfolioSummary => usPortfolioSummary;

  PortfolioSummary get selectedPortfolioSummary =>
      selectedPortfolioMarket == PortfolioMarket.kr
          ? krPortfolioSummary
          : usPortfolioSummary;

  List<PortfolioPositionManagementItem> get selectedPortfolioManagementItems =>
      portfolioManagementItemsForMarket(selectedPortfolioMarket);

  List<PortfolioPositionManagementItem> portfolioManagementItemsForMarket(
    PortfolioMarket market,
  ) {
    final marketCode = market == PortfolioMarket.kr ? 'KR' : 'US';
    final existing = portfolioManagementItems
        .where((item) => item.market.toUpperCase() == marketCode)
        .toList();
    if (existing.isNotEmpty) return existing;

    final items = _buildPortfolioManagementItemsFor(
      market == PortfolioMarket.kr ? krPortfolioSummary : usPortfolioSummary,
      isKr: market == PortfolioMarket.kr,
    );
    items.sort(PortfolioPositionManagementItem.comparePriority);
    return items;
  }

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
  bool kisAutomationSettingsLoading = false;
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
      await refreshSchedulerStatus(silent: true);
      await refreshAgentChatLiveOrderReadiness(silent: true);
      await refreshKisSchedulerStatus(silent: true);
      await loadMarketWatchlists();
      await _refreshPortfolioSummaries();
      _rebuildPortfolioManagementItems();
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
      await _loadHomeRecentActivity();
      _rebuildAutomationRuntimeMonitorFromCurrentState();
      _rebuildPortfolioManagementItems();
    } catch (e) {
      error = e.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> _loadHomeRecentActivity() async {
    try {
      final runs = await apiClient.fetchRecentRuns(limit: 3);
      automationRecentRuns = runs;
      recentRuns = runs.map(_tradingRunFromLog).toList();
    } catch (_) {
      automationRecentRuns = const [];
      recentRuns = const [];
    }

    try {
      automationRecentOrders = await apiClient.fetchRecentOrders(limit: 3);
    } catch (_) {
      automationRecentOrders = const [];
    }
  }

  Future<ActionResult> refreshSchedulerStatus({bool silent = false}) async {
    if (schedulerStatusLoading) {
      return const ActionResult(
        success: false,
        message: 'Scheduler status refresh already in progress.',
      );
    }

    schedulerStatusLoading = true;
    if (!silent) notifyListeners();

    try {
      schedulerStatus = await apiClient.fetchSchedulerStatus();
      schedulerStatusLoaded = true;
      schedulerStatusError = null;
      _rebuildAutomationRuntimeMonitorFromCurrentState();
      _rebuildPortfolioManagementItems();
      return const ActionResult(
        success: true,
        message: 'Operational readiness refreshed.',
      );
    } catch (e) {
      schedulerStatusError =
          'Operational readiness unavailable: ${ApiErrorFormatter.format(e.toString())}';
      return ActionResult(success: false, message: schedulerStatusError!);
    } finally {
      schedulerStatusLoading = false;
      if (!silent) notifyListeners();
    }
  }

  Future<ActionResult> refreshAllOperationsOverview() async {
    final monitor = await refreshAutomationRuntimeMonitor(silent: true);
    final portfolio = await refreshPortfolioManagement(silent: true);
    notifyListeners();
    if (!monitor.success) return monitor;
    if (!portfolio.success) return portfolio;
    return const ActionResult(
      success: true,
      message: 'Operations overview refreshed.',
    );
  }

  Future<ActionResult> refreshAutomationRuntimeMonitor({
    bool silent = false,
  }) async {
    if (automationRuntimeMonitorLoading) {
      return const ActionResult(
        success: false,
        message: 'Automation runtime monitor refresh already in progress.',
      );
    }

    automationRuntimeMonitorLoading = true;
    automationRuntimeMonitorError = null;
    if (!silent) notifyListeners();

    final warnings = <String>[];
    var nextSettings = settings;
    var nextSchedulerStatus = schedulerStatus;
    var nextKisSchedulerStatus = kisSchedulerStatus;
    var nextRuns = automationRecentRuns;
    var nextOrders = automationRecentOrders;
    var nextSignals = automationRecentSignals;
    var nextGuardedSell = latestKisSchedulerGuardedSellResult;
    var nextGuardedBuy = latestKisSchedulerGuardedBuyResult;

    try {
      nextSettings = await apiClient.getOpsSettings();
      settings = nextSettings;
      kisSafetyStatus = kisSafetyStatusFromSettings();
    } catch (e) {
      warnings.add('ops settings unavailable');
    }

    try {
      nextSchedulerStatus = await apiClient.fetchSchedulerStatus();
      schedulerStatus = nextSchedulerStatus;
      schedulerStatusLoaded = true;
      schedulerStatusError = null;
    } catch (e) {
      warnings.add('scheduler status unavailable');
      schedulerStatusError =
          'Operational readiness unavailable: ${ApiErrorFormatter.format(e.toString())}';
    }

    try {
      nextKisSchedulerStatus = await apiClient.fetchKisSchedulerStatus();
      kisSchedulerStatus = nextKisSchedulerStatus;
      kisSchedulerStatusLoaded = true;
      kisSchedulerStatusError = null;
    } catch (e) {
      warnings.add('KIS scheduler status unavailable');
      kisSchedulerStatusError = ApiErrorFormatter.format(e.toString());
    }

    try {
      nextRuns = await apiClient.fetchRecentRuns(limit: 50);
      automationRecentRuns = nextRuns;
      recentRuns = nextRuns.map(_tradingRunFromLog).toList();
    } catch (e) {
      warnings.add('recent runs unavailable');
    }

    try {
      nextOrders = await apiClient.fetchRecentOrders(limit: 50);
      automationRecentOrders = nextOrders;
    } catch (e) {
      warnings.add('recent orders unavailable');
    }

    try {
      nextSignals = await apiClient.fetchRecentSignals(limit: 50);
      automationRecentSignals = nextSignals;
    } catch (e) {
      warnings.add('recent signals unavailable');
    }

    try {
      nextGuardedSell = await apiClient.fetchKisSchedulerGuardedSellStatus();
      latestKisSchedulerGuardedSellResult = nextGuardedSell;
      kisSchedulerGuardedSellError = null;
    } catch (e) {
      warnings.add('KIS guarded sell status unavailable');
      kisSchedulerGuardedSellError = ApiErrorFormatter.format(e.toString());
    }

    try {
      nextGuardedBuy = await apiClient.fetchKisSchedulerGuardedBuyStatus();
      latestKisSchedulerGuardedBuyResult = nextGuardedBuy;
      kisSchedulerGuardedBuyError = null;
    } catch (e) {
      warnings.add('KIS guarded buy status unavailable');
      kisSchedulerGuardedBuyError = ApiErrorFormatter.format(e.toString());
    }

    automationRuntimeMonitor = AutomationRuntimeMonitor.fromSources(
      settings: nextSettings,
      schedulerStatus: nextSchedulerStatus,
      selectedProvider: selectedBrokerLabel,
      currentLocalTime: _localTimestampNow(),
      lastRefreshTime: _localTimestampNow(),
      kisSchedulerStatus: nextKisSchedulerStatus,
      guardedSell: nextGuardedSell,
      guardedBuy: nextGuardedBuy,
      runs: nextRuns,
      orders: nextOrders,
      signals: nextSignals,
      localEvents: localAutomationEvents,
      warnings: warnings,
    );
    _rebuildPortfolioManagementItems();
    automationRuntimeMonitorError =
        warnings.isEmpty ? null : warnings.join(' | ');
    automationRuntimeMonitorLoading = false;
    notifyListeners();

    if (warnings.isNotEmpty) {
      return ActionResult(
        success: false,
        message: 'Automation monitor refreshed with partial data.',
      );
    }
    return const ActionResult(
      success: true,
      message: 'Automation monitor refreshed.',
    );
  }

  Future<ActionResult> refreshPortfolioManagement({
    bool silent = false,
  }) async {
    if (portfolioManagementLoading) {
      return const ActionResult(
        success: false,
        message: 'Portfolio management refresh already in progress.',
      );
    }

    portfolioManagementLoading = true;
    portfolioManagementError = null;
    if (!silent) notifyListeners();
    try {
      await _refreshPortfolioSummaries();
      _rebuildPortfolioManagementItems();
      return const ActionResult(
        success: true,
        message: 'Portfolio management refreshed.',
      );
    } catch (e) {
      portfolioManagementError =
          'Portfolio management unavailable: ${ApiErrorFormatter.format(e.toString())}';
      _rebuildPortfolioManagementItems();
      return ActionResult(
        success: false,
        message: _primaryMessage(portfolioManagementError!),
      );
    } finally {
      portfolioManagementLoading = false;
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

  Future<ActionResult> runAlpacaWatchlistCheck() async {
    if (runOnceLoading) {
      return const ActionResult(
        success: false,
        message: 'Alpaca watchlist check already in progress.',
      );
    }

    runOnceLoading = true;
    error = null;
    notifyListeners();
    try {
      final result = await apiClient.runWatchlistForProvider(
        provider: 'alpaca',
        gateLevel: selectedGateLevel,
      );
      runResult = result;
      hasLatestRunResult = true;
      showingOfflineFallback = false;
      recentRuns = await apiClient.getRecentTradingRuns();
      await _refreshUsPortfolioSummary();
      return ActionResult(
        success: true,
        message:
            'Alpaca paper watchlist check completed: ${result.reason.isEmpty ? result.result : result.reason}.',
      );
    } catch (e) {
      error = 'Alpaca paper watchlist check failed: $e';
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
      await refreshSchedulerStatus(silent: true);
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
      await refreshSchedulerStatus(silent: true);
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
      await refreshSchedulerStatus(silent: true);
      _recordSettingsChangeEvent('Dry Run', {'dry_run': v});
      _rebuildAutomationRuntimeMonitorFromCurrentState();
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

  Future<ActionResult> updateKisAutomationSettings(
    Map<String, dynamic> values, {
    String label = 'KIS automation setting',
  }) async {
    final previousSettings = settings;
    settings = _opsSettingsWithPayload(settings, values);
    kisSafetyStatus = kisSafetyStatusFromSettings();
    kisAutomationSettingsLoading = true;
    error = null;
    notifyListeners();

    try {
      await apiClient.updateOpsSettings(values);
      settings = await apiClient.getOpsSettings();
      kisSafetyStatus = kisSafetyStatusFromSettings();
      await refreshSchedulerStatus(silent: true);
      await _refreshKisSchedulerGuardedStatusesAfterSettingsUpdate();
      _recordSettingsChangeEvent(label, values);
      _rebuildAutomationRuntimeMonitorFromCurrentState();
      _rebuildPortfolioManagementItems();
      return ActionResult(
        success: true,
        message: '$label updated successfully. Monitor refreshed.',
      );
    } catch (e) {
      settings = previousSettings;
      kisSafetyStatus = kisSafetyStatusFromSettings();
      final message =
          '$label update failed: ${ApiErrorFormatter.format(e.toString())}';
      try {
        settings = await apiClient.getOpsSettings();
        kisSafetyStatus = kisSafetyStatusFromSettings();
        await refreshSchedulerStatus(silent: true);
      } catch (_) {
        // Keep the rollback state when the backend refresh is unavailable.
      }
      error = message;
      return ActionResult(success: false, message: error!);
    } finally {
      kisAutomationSettingsLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> applyOperationModePreset(
    String preset, {
    bool confirmDangerous = false,
  }) async {
    final previousSettings = settings;
    kisAutomationSettingsLoading = true;
    error = null;
    notifyListeners();

    try {
      final payload = await apiClient.applyOpsSettingsPreset(
        preset: preset,
        confirmDangerous: confirmDangerous,
      );
      if (payload['requires_confirmation'] == true &&
          payload['applied'] != true) {
        return const ActionResult(
          success: false,
          message: 'Full Live Test Mode requires confirmation.',
        );
      }
      settings = await apiClient.getOpsSettings();
      kisSafetyStatus = kisSafetyStatusFromSettings();
      await refreshSchedulerStatus(silent: true);
      await _refreshKisSchedulerGuardedStatusesAfterSettingsUpdate();
      _recordSettingsChangeEvent(_operationModeLabel(preset), {
        'operation_mode': preset,
        'confirm_dangerous': confirmDangerous,
      });
      _rebuildAutomationRuntimeMonitorFromCurrentState();
      _rebuildPortfolioManagementItems();
      return ActionResult(
        success: true,
        message: '${_operationModeLabel(preset)} applied.',
      );
    } catch (e) {
      settings = previousSettings;
      kisSafetyStatus = kisSafetyStatusFromSettings();
      final message =
          '${_operationModeLabel(preset)} failed: ${ApiErrorFormatter.format(e.toString())}';
      try {
        settings = await apiClient.getOpsSettings();
        kisSafetyStatus = kisSafetyStatusFromSettings();
        await refreshSchedulerStatus(silent: true);
      } catch (_) {
        // Keep the rollback state when backend refresh is unavailable.
      }
      error = message;
      return ActionResult(success: false, message: error!);
    } finally {
      kisAutomationSettingsLoading = false;
      notifyListeners();
    }
  }

  Future<void> _refreshKisSchedulerGuardedStatusesAfterSettingsUpdate() async {
    try {
      latestKisSchedulerGuardedSellResult =
          await apiClient.fetchKisSchedulerGuardedSellStatus();
      kisSchedulerGuardedSellError = null;
    } catch (_) {
      // Settings update should not fail only because status refresh is unavailable.
    }
    try {
      latestKisSchedulerGuardedBuyResult =
          await apiClient.fetchKisSchedulerGuardedBuyStatus();
      kisSchedulerGuardedBuyError = null;
    } catch (_) {
      // Settings update should not fail only because status refresh is unavailable.
    }
  }

  void _recordSettingsChangeEvent(String label, Map<String, dynamic> values) {
    final summary = _settingsChangeSummary(label, settings, schedulerStatus);
    latestSettingsChangeSummary = summary;
    final event = AutomationEvent.settingsChanged(
      id: 'settings-${DateTime.now().microsecondsSinceEpoch}',
      timestamp: _localTimestampNow(),
      title: label,
      reason: summary,
      payload: {
        'label': label,
        'updated_values': Map<String, dynamic>.from(values),
        'settings_summary': summary,
      },
    );
    localAutomationEvents = [event, ...localAutomationEvents].take(20).toList();
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
    kisTradingSourceContext = null;
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
    kisTradingSourceContext = null;
    kisSingleSymbolTradingError = null;
    notifyListeners();
  }

  void setKisGuardedRunConfirmation(bool value) {
    kisGuardedRunConfirmation = value;
    notifyListeners();
  }

  void setAgentChatMode(AgentChatPanelMode mode) {
    if (agentChatMode == mode) return;
    agentChatMode = mode;
    notifyListeners();
  }

  void cycleAgentChatMode() {
    switch (agentChatMode) {
      case AgentChatPanelMode.collapsed:
        setAgentChatMode(AgentChatPanelMode.mini);
        return;
      case AgentChatPanelMode.mini:
        setAgentChatMode(AgentChatPanelMode.expanded);
        return;
      case AgentChatPanelMode.expanded:
        setAgentChatMode(AgentChatPanelMode.fullscreen);
        return;
      case AgentChatPanelMode.fullscreen:
        setAgentChatMode(AgentChatPanelMode.mini);
        return;
    }
  }

  void clearAgentChat() {
    clearCurrentAgentChatLocal();
  }

  void clearCurrentAgentChatLocal() {
    agentMessages = _defaultAgentSafetyMessages(appLanguage);
    latestAgentCommand = null;
    latestAgentPlan = null;
    latestAgentRun = null;
    latestAgentPrefill = null;
    agentErrorMessage = null;
    notifyListeners();
  }

  Future<ActionResult> initializeAgentConversation() async {
    if (activeAgentConversationKey != null || isLoadingAgentHistory) {
      return const ActionResult(success: true, message: 'Agent chat is ready.');
    }
    return restoreLatestAgentConversation();
  }

  Future<ActionResult> restoreLatestAgentConversation() async {
    isLoadingAgentHistory = true;
    agentHistoryError = null;
    notifyListeners();
    try {
      agentConversations = await apiClient.fetchAgentChatConversations(
        status: 'active',
        limit: 20,
      );
      if (agentConversations.isEmpty) {
        final conversation = await apiClient.createAgentChatConversation(
          source: 'flutter_dashboard',
          metadata: const {'source': 'flutter_dashboard'},
        );
        activeAgentConversationKey = conversation.conversationKey;
        agentConversations = [conversation];
        return const ActionResult(
          success: true,
          message: 'New agent conversation created.',
        );
      }
      final latest = agentConversations.first;
      await loadAgentConversationHistory(latest.conversationKey, silent: true);
      return const ActionResult(
        success: true,
        message: 'Agent conversation restored.',
      );
    } catch (e) {
      agentHistoryError =
          'Chat history unavailable; continuing local-only. ${ApiErrorFormatter.format(e.toString())}';
      activeAgentConversationKey ??= agentConversationId;
      return ActionResult(
          success: false, message: _primaryMessage(agentHistoryError!));
    } finally {
      isLoadingAgentHistory = false;
      notifyListeners();
    }
  }

  Future<ActionResult> loadAgentConversationHistory(
    String conversationKey, {
    bool silent = false,
  }) async {
    if (!silent) {
      isLoadingAgentHistory = true;
      agentHistoryError = null;
      notifyListeners();
    }
    try {
      activeAgentConversationKey = conversationKey;
      final messages = await apiClient.fetchAgentChatMessages(
        conversationKey,
        limit: 100,
      );
      agentMessages = messages.isEmpty
          ? _defaultAgentSafetyMessages(appLanguage)
          : messages;
      return const ActionResult(
        success: true,
        message: 'Agent chat history loaded.',
      );
    } catch (e) {
      agentHistoryError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
          success: false, message: _primaryMessage(agentHistoryError!));
    } finally {
      if (!silent) {
        isLoadingAgentHistory = false;
        notifyListeners();
      }
    }
  }

  Future<ActionResult> startNewAgentConversation() async {
    isLoadingAgentHistory = true;
    agentHistoryError = null;
    notifyListeners();
    try {
      final conversation = await apiClient.createAgentChatConversation(
        source: 'flutter_dashboard',
        metadata: const {'source': 'flutter_dashboard'},
      );
      activeAgentConversationKey = conversation.conversationKey;
      agentConversations = [conversation, ...agentConversations]
          .where((item) => item.status == 'active')
          .toList();
      latestAgentCommand = null;
      latestAgentPlan = null;
      latestAgentRun = null;
      latestAgentPrefill = null;
      agentMessages = _defaultAgentSafetyMessages(appLanguage);
      return const ActionResult(
          success: true, message: 'New agent chat started.');
    } catch (e) {
      agentHistoryError = ApiErrorFormatter.format(e.toString());
      clearCurrentAgentChatLocal();
      return ActionResult(
          success: false, message: _primaryMessage(agentHistoryError!));
    } finally {
      isLoadingAgentHistory = false;
      notifyListeners();
    }
  }

  Future<ActionResult> archiveAgentConversation() async {
    final key = activeAgentConversationKey;
    if (key == null || key.isEmpty) {
      clearCurrentAgentChatLocal();
      return const ActionResult(success: true, message: 'Local chat cleared.');
    }
    isLoadingAgentHistory = true;
    agentHistoryError = null;
    notifyListeners();
    try {
      await apiClient.archiveAgentChatConversation(key);
      activeAgentConversationKey = null;
      agentConversations = agentConversations
          .where((item) => item.conversationKey != key)
          .toList();
      latestAgentCommand = null;
      latestAgentPlan = null;
      latestAgentRun = null;
      latestAgentPrefill = null;
      agentMessages = _defaultAgentSafetyMessages(appLanguage);
      return const ActionResult(
        success: true,
        message: 'Agent conversation archived.',
      );
    } catch (e) {
      agentHistoryError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
          success: false, message: _primaryMessage(agentHistoryError!));
    } finally {
      isLoadingAgentHistory = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshAgentOperationsSummary() async {
    isLoadingAgentOperations = true;
    agentOperationsError = null;
    notifyListeners();
    try {
      agentOperationsSnapshot = await apiClient.fetchAgentOperationsSummary();
      return const ActionResult(
        success: true,
        message: 'Agent operations summary refreshed.',
      );
    } catch (e) {
      agentOperationsError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(agentOperationsError!),
      );
    } finally {
      isLoadingAgentOperations = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshAgentChatLiveOrderReadiness({
    bool silent = false,
  }) async {
    if (isLoadingAgentChatLiveOrderReadiness) {
      return const ActionResult(
        success: false,
        message: 'Agent Chat live-order readiness refresh already in progress.',
      );
    }

    isLoadingAgentChatLiveOrderReadiness = true;
    agentChatLiveOrderSettingsError = null;
    if (!silent) notifyListeners();

    try {
      agentChatLiveOrderReadiness =
          await apiClient.fetchAgentChatLiveOrderReadiness();
      return const ActionResult(
        success: true,
        message: 'Agent Chat live-order readiness refreshed.',
      );
    } catch (e) {
      agentChatLiveOrderSettingsError =
          'Agent Chat live-order readiness unavailable: ${ApiErrorFormatter.format(e.toString())}';
      return ActionResult(
        success: false,
        message: _primaryMessage(agentChatLiveOrderSettingsError!),
      );
    } finally {
      isLoadingAgentChatLiveOrderReadiness = false;
      if (!silent) notifyListeners();
    }
  }

  Future<ActionResult> applyAgentChatLiveOrderPreset(String preset) async {
    if (applyingAgentChatLiveOrderPreset != null) {
      return const ActionResult(
        success: false,
        message: 'Agent Chat live-order preset already in progress.',
      );
    }

    applyingAgentChatLiveOrderPreset = preset;
    agentChatLiveOrderSettingsError = null;
    notifyListeners();

    try {
      final result = await apiClient.applyAgentChatLiveOrderPreset(preset);
      if (result.readiness != null) {
        agentChatLiveOrderReadiness = result.readiness;
      } else {
        agentChatLiveOrderReadiness =
            await apiClient.fetchAgentChatLiveOrderReadiness();
      }
      try {
        settings = await apiClient.getOpsSettings();
        kisSafetyStatus = kisSafetyStatusFromSettings();
      } catch (_) {
        // Agent Chat preset success should not be hidden by a secondary settings refresh.
      }
      return ActionResult(
        success: true,
        message: _agentChatPresetAppliedMessage(preset, result.changedKeys),
      );
    } catch (e) {
      agentChatLiveOrderSettingsError =
          'Agent Chat live-order preset failed: ${ApiErrorFormatter.format(e.toString())}';
      return ActionResult(
        success: false,
        message: _primaryMessage(agentChatLiveOrderSettingsError!),
      );
    } finally {
      applyingAgentChatLiveOrderPreset = null;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshStrategyProfiles({bool silent = false}) async {
    if (strategyProfilesLoading) {
      return const ActionResult(
        success: false,
        message: 'Strategy profiles are already loading.',
      );
    }

    strategyProfilesLoading = true;
    strategyProfileError = null;
    if (!silent) notifyListeners();

    try {
      final result = await apiClient.fetchStrategyProfiles();
      strategyProfiles = result.profiles;
      activeStrategyProfile = result.activeProfile;
      return ActionResult(
        success: true,
        message:
            'Strategy profiles refreshed: ${result.activeProfile.displayName}.',
      );
    } catch (e) {
      strategyProfileError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyProfileError!),
      );
    } finally {
      strategyProfilesLoading = false;
      if (!silent) notifyListeners();
    }
  }

  Future<ActionResult> applyStrategyProfilePreset(String profileName) async {
    final normalized = profileName.trim().toLowerCase();
    if (applyingStrategyProfileName != null) {
      return const ActionResult(
        success: false,
        message: 'A strategy profile change is already running.',
      );
    }

    applyingStrategyProfileName = normalized;
    strategyProfileError = null;
    notifyListeners();

    try {
      final result = await apiClient.applyStrategyProfilePreset(normalized);
      activeStrategyProfile = result.activeProfile;
      if (strategyProfiles.isNotEmpty) {
        strategyProfiles = [
          for (final profile in strategyProfiles)
            StrategyProfile.fromJson({
              ...profile.toJson(),
              'is_active':
                  profile.profileName == result.activeProfile.profileName,
            }),
        ];
      } else {
        await refreshStrategyProfiles(silent: true);
      }
      return ActionResult(
        success: true,
        message:
            '${result.activeProfile.displayName} strategy profile applied. No order submitted.',
      );
    } catch (e) {
      strategyProfileError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyProfileError!),
      );
    } finally {
      applyingStrategyProfileName = null;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshStrategyPerformance({
    bool silent = false,
  }) async {
    if (strategyPerformanceLoading) {
      return const ActionResult(
        success: false,
        message: 'Strategy performance is already loading.',
      );
    }
    strategyPerformanceLoading = true;
    strategyPerformanceError = null;
    if (!silent) notifyListeners();
    try {
      final results = await Future.wait<Object>([
        apiClient.fetchStrategyDailyPerformance(),
        apiClient.fetchStrategyMonthlyPerformance(),
        apiClient.fetchStrategyTradePerformance(limit: 10),
      ]);
      strategyDailyPerformance = results[0] as StrategyDailyPerformance;
      strategyMonthlyPerformance = results[1] as StrategyMonthlyPerformance;
      strategyTradePerformance = results[2] as StrategyTradePerformanceList;
      return const ActionResult(
        success: true,
        message: 'Strategy performance refreshed.',
      );
    } catch (e) {
      strategyPerformanceError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyPerformanceError!),
      );
    } finally {
      strategyPerformanceLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshStrategyRiskState({
    bool silent = false,
  }) async {
    if (strategyRiskLoading) {
      return const ActionResult(
        success: false,
        message: 'Strategy risk state is already loading.',
      );
    }
    strategyRiskLoading = true;
    strategyRiskError = null;
    if (!silent) notifyListeners();
    try {
      strategyRiskState = await apiClient.fetchStrategyRiskState();
      return const ActionResult(
        success: true,
        message: 'Target-aware risk state refreshed.',
      );
    } catch (e) {
      strategyRiskError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyRiskError!),
      );
    } finally {
      strategyRiskLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runStrategyDryRunAutoBuy() async {
    if (strategyDryRunAutoBuyLoading) {
      return const ActionResult(
        success: false,
        message: 'Strategy dry-run auto buy is already running.',
      );
    }
    strategyDryRunAutoBuyLoading = true;
    strategyDryRunAutoBuyError = null;
    notifyListeners();
    try {
      final result = await apiClient.runStrategyDryRunAutoBuy(
        profileName: activeStrategyProfile?.profileName,
      );
      strategyDryRunAutoBuyResult = result;
      final recent =
          await apiClient.fetchStrategyDryRunAutoBuyRecent(limit: 10);
      strategyDryRunAutoBuyRecent = recent.items;
      return ActionResult(
        success: true,
        message: 'Dry-run auto buy completed: ${result.action}.',
      );
    } catch (e) {
      strategyDryRunAutoBuyError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyDryRunAutoBuyError!),
      );
    } finally {
      strategyDryRunAutoBuyLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshStrategyDryRunAutoBuy({
    bool silent = false,
  }) async {
    if (strategyDryRunAutoBuyLoading) {
      return const ActionResult(
        success: false,
        message: 'Strategy dry-run results are already loading.',
      );
    }
    strategyDryRunAutoBuyLoading = true;
    strategyDryRunAutoBuyError = null;
    if (!silent) notifyListeners();
    try {
      final recent =
          await apiClient.fetchStrategyDryRunAutoBuyRecent(limit: 10);
      strategyDryRunAutoBuyRecent = recent.items;
      strategyDryRunAutoBuyResult = recent.latest;
      return ActionResult(
        success: true,
        message: 'Recent dry-run results refreshed: ${recent.items.length}.',
      );
    } catch (e) {
      strategyDryRunAutoBuyError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyDryRunAutoBuyError!),
      );
    } finally {
      strategyDryRunAutoBuyLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runStrategyLiveAutoBuyOnce() async {
    if (strategyLiveAutoBuyLoading) {
      return const ActionResult(
        success: false,
        message: 'Strategy live auto buy is already running.',
      );
    }
    if (strategyLiveAutoBuyReadiness?.ready != true) {
      final reason =
          strategyLiveAutoBuyReadiness?.primaryBlockReason ?? 'not_ready';
      return ActionResult(
        success: false,
        message: 'Guarded live auto buy is blocked: $reason.',
      );
    }
    strategyLiveAutoBuyLoading = true;
    strategyLiveAutoBuyError = null;
    notifyListeners();
    try {
      final requestId =
          'flutter-live-auto-buy-${DateTime.now().millisecondsSinceEpoch}';
      final result = await apiClient.runStrategyLiveAutoBuyOnce(
        symbol: strategyLiveAutoBuyReadiness?.selectedSymbol,
        clientRequestId: requestId,
      );
      strategyLiveAutoBuyResult = result;
      final results = await Future.wait<Object>([
        apiClient.fetchStrategyLiveAutoBuyReadiness(),
        apiClient.fetchStrategyLiveAutoBuyRecent(limit: 10),
      ]);
      strategyLiveAutoBuyReadiness = results[0] as StrategyLiveAutoBuyReadiness;
      final recent = results[1] as StrategyLiveAutoBuyRecent;
      strategyLiveAutoBuyRecent = recent.items;
      return ActionResult(
        success: result.submitted,
        message: result.submitted
            ? 'Guarded live auto buy submitted: ${result.symbol ?? '-'}.'
            : 'Guarded live auto buy blocked: ${result.blockReason ?? result.status}.',
      );
    } catch (e) {
      strategyLiveAutoBuyError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyLiveAutoBuyError!),
      );
    } finally {
      strategyLiveAutoBuyLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshStrategyLiveAutoBuy({
    bool silent = false,
  }) async {
    if (strategyLiveAutoBuyLoading) {
      return const ActionResult(
        success: false,
        message: 'Strategy live auto buy status is already loading.',
      );
    }
    strategyLiveAutoBuyLoading = true;
    strategyLiveAutoBuyError = null;
    if (!silent) notifyListeners();
    try {
      final results = await Future.wait<Object>([
        apiClient.fetchStrategyLiveAutoBuyReadiness(),
        apiClient.fetchStrategyLiveAutoBuyRecent(limit: 10),
      ]);
      strategyLiveAutoBuyReadiness = results[0] as StrategyLiveAutoBuyReadiness;
      final recent = results[1] as StrategyLiveAutoBuyRecent;
      strategyLiveAutoBuyRecent = recent.items;
      strategyLiveAutoBuyResult = recent.latest;
      return ActionResult(
        success: true,
        message:
            'Guarded live auto buy status refreshed: ${recent.items.length}.',
      );
    } catch (e) {
      strategyLiveAutoBuyError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyLiveAutoBuyError!),
      );
    } finally {
      strategyLiveAutoBuyLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshPositionExitReview({
    bool silent = false,
  }) async {
    if (positionExitReviewLoading) {
      return const ActionResult(
        success: false,
        message: 'Position exit review is already loading.',
      );
    }
    positionExitReviewLoading = true;
    positionExitReviewError = null;
    if (!silent) notifyListeners();
    try {
      positionExitReview = await apiClient.fetchPositionExitReview();
      return ActionResult(
        success: true,
        message:
            'Position exit review refreshed: ${positionExitReview!.positions.length}.',
      );
    } catch (e) {
      positionExitReviewError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(positionExitReviewError!),
      );
    } finally {
      positionExitReviewLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshAutoExitCandidates({
    bool silent = false,
    String? minSeverity,
  }) async {
    if (autoExitCandidatesLoading) {
      return ActionResult(
        success: false,
        message: strings.autoExitCandidatesAlreadyLoading,
      );
    }
    autoExitCandidatesLoading = true;
    autoExitCandidatesError = null;
    if (!silent) notifyListeners();
    try {
      autoExitCandidates = await apiClient.fetchAutoExitCandidates(
        provider: selectedProviderCode,
        market: selectedMarketCode,
        minSeverity: minSeverity,
      );
      return ActionResult(
        success: true,
        message: strings.autoExitCandidatesRefreshed(
          autoExitCandidates!.summary.candidateCount,
        ),
      );
    } catch (e) {
      autoExitCandidatesError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(autoExitCandidatesError!),
      );
    } finally {
      autoExitCandidatesLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshPositionManagementDryRun({
    bool silent = false,
  }) async {
    if (positionManagementDryRunLoading) {
      return ActionResult(
        success: false,
        message: strings.positionManagementDryRunAlreadyLoading,
      );
    }
    positionManagementDryRunLoading = true;
    positionManagementDryRunError = null;
    if (!silent) notifyListeners();
    try {
      positionManagementDryRun =
          await apiClient.fetchPositionManagementDryRunLatest(
        provider: selectedProviderCode,
        market: selectedMarketCode,
      );
      return ActionResult(
        success: true,
        message: strings.positionManagementDryRunRefreshed(
          positionManagementDryRun!.exitCandidateCount,
        ),
      );
    } catch (e) {
      positionManagementDryRunError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(positionManagementDryRunError!),
      );
    } finally {
      positionManagementDryRunLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runPositionManagementDryRunOnce() async {
    if (positionManagementDryRunLoading) {
      return ActionResult(
        success: false,
        message: strings.positionManagementDryRunAlreadyLoading,
      );
    }
    positionManagementDryRunLoading = true;
    positionManagementDryRunError = null;
    notifyListeners();
    try {
      positionManagementDryRun =
          await apiClient.runPositionManagementDryRunOnce(
        provider: selectedProviderCode,
        market: selectedMarketCode,
      );
      return ActionResult(
        success: positionManagementDryRun!.resultStatus != 'error',
        message: strings.positionManagementDryRunCompleted(
          positionManagementDryRun!.resultStatus,
          positionManagementDryRun!.exitCandidateCount,
        ),
      );
    } catch (e) {
      positionManagementDryRunError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(positionManagementDryRunError!),
      );
    } finally {
      positionManagementDryRunLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshPositionLifecycle({
    bool silent = false,
    String status = 'all',
  }) async {
    if (positionLifecycleLoading) {
      return const ActionResult(
        success: false,
        message: 'Position lifecycle is already loading.',
      );
    }
    positionLifecycleLoading = true;
    positionLifecycleError = null;
    if (!silent) notifyListeners();
    try {
      positionLifecycle = await apiClient.fetchPositionLifecycle(
        status: status,
      );
      return ActionResult(
        success: true,
        message: strings.positionLifecycleRefreshed(
          positionLifecycle!.items.length,
        ),
      );
    } catch (e) {
      positionLifecycleError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(positionLifecycleError!),
      );
    } finally {
      positionLifecycleLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runPositionSellPreflight(
    PositionExitReviewItem position,
  ) async {
    if (positionSellPreflightLoading) {
      return ActionResult(
        success: false,
        message: strings.sellPreflightAlreadyRunning,
      );
    }
    positionSellPreflightLoading = true;
    positionSellPreflightError = null;
    notifyListeners();
    try {
      final result = await apiClient.runPositionSellPreflight(
        symbol: position.symbol,
        language: appLanguage.code,
        locale: appLanguage.localeCode,
      );
      latestPositionSellPreflight = result;
      latestGuardedPositionSellResult = null;
      return ActionResult(
        success: !result.isBlocked,
        message: strings.sellPreflightCompletedMessage(
          result.preflightStatus,
          result.primaryBlockReason,
        ),
      );
    } catch (e) {
      positionSellPreflightError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(positionSellPreflightError!),
      );
    } finally {
      positionSellPreflightLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runAutoExitCandidateSellPreflight(
    AutoExitCandidate candidate,
  ) async {
    if (!candidate.canRunSellPreflight) {
      return ActionResult(
        success: false,
        message: strings.sellPreflightBlockedForCandidate(
          candidate.syncRequired
              ? strings.syncRequired
              : candidate.openSellOrderConflict
                  ? strings.duplicateSellOrder
                  : candidate.primaryReason,
        ),
      );
    }
    if (positionSellPreflightLoading) {
      return ActionResult(
        success: false,
        message: strings.sellPreflightAlreadyRunning,
      );
    }
    positionSellPreflightLoading = true;
    positionSellPreflightError = null;
    notifyListeners();
    try {
      final result = await apiClient.runPositionSellPreflight(
        symbol: candidate.symbol,
        provider: candidate.provider,
        market: candidate.market,
        language: appLanguage.code,
        locale: appLanguage.localeCode,
      );
      latestPositionSellPreflight = result;
      latestGuardedPositionSellResult = null;
      return ActionResult(
        success: !result.isBlocked,
        message: strings.sellPreflightCompletedMessage(
          result.preflightStatus,
          result.primaryBlockReason,
        ),
      );
    } catch (e) {
      positionSellPreflightError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(positionSellPreflightError!),
      );
    } finally {
      positionSellPreflightLoading = false;
      notifyListeners();
    }
  }

  void clearPositionSellPreflight() {
    latestPositionSellPreflight = null;
    latestGuardedPositionSellResult = null;
    positionSellPreflightError = null;
    guardedPositionSellError = null;
    notifyListeners();
  }

  Future<ActionResult> executeGuardedPositionSell(
    PositionSellPreflightResult preflight,
  ) async {
    if (guardedPositionSellLoading) {
      return ActionResult(
        success: false,
        message: strings.guardedLiveSellAlreadyRunning,
      );
    }
    if (!preflight.canSubmitAfterConfirmation) {
      return ActionResult(
        success: false,
        message: strings.preflightBlocksGuardedSell(
          preflight.primaryBlockReason ?? preflight.preflightStatus,
        ),
      );
    }
    guardedPositionSellLoading = true;
    guardedPositionSellError = null;
    notifyListeners();
    try {
      final quantityMode = _guardedSellQuantityMode(preflight);
      final result = await apiClient.runGuardedPositionSell(
        symbol: preflight.symbol,
        provider: preflight.provider,
        market: preflight.market,
        quantityMode: quantityMode,
        quantity:
            quantityMode == 'partial' ? preflight.requestedQuantity : null,
        confirmLive: true,
        clientRequestId:
            'guarded-sell-${preflight.symbol}-${DateTime.now().millisecondsSinceEpoch}',
        language: appLanguage.code,
        locale: appLanguage.localeCode,
        reason: _guardedSellReason(preflight),
      );
      latestGuardedPositionSellResult = result;
      return ActionResult(
        success: !result.isBlocked,
        message: strings.guardedLiveSellCompletedMessage(
          result.resultStatus,
          result.primaryBlockReason,
        ),
      );
    } catch (e) {
      guardedPositionSellError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(guardedPositionSellError!),
      );
    } finally {
      guardedPositionSellLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshGuardedPositionSellResult() async {
    final attemptId = latestGuardedPositionSellResult?.attemptId;
    if (attemptId == null) {
      return ActionResult(
        success: false,
        message: strings.guardedLiveSellResultUnavailable,
      );
    }
    if (guardedPositionSellLoading) {
      return ActionResult(
        success: false,
        message: strings.guardedLiveSellAlreadyRunning,
      );
    }
    guardedPositionSellLoading = true;
    guardedPositionSellError = null;
    notifyListeners();
    try {
      final result = await apiClient.fetchGuardedPositionSellResult(attemptId);
      latestGuardedPositionSellResult = result;
      return ActionResult(
        success: true,
        message: strings.guardedLiveSellResultRefreshed(result.resultStatus),
      );
    } catch (e) {
      guardedPositionSellError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(guardedPositionSellError!),
      );
    } finally {
      guardedPositionSellLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> syncGuardedPositionSellResult() async {
    final attemptId = latestGuardedPositionSellResult?.attemptId;
    if (attemptId == null) {
      return ActionResult(
        success: false,
        message: strings.guardedLiveSellResultUnavailable,
      );
    }
    if (guardedPositionSellLoading) {
      return ActionResult(
        success: false,
        message: strings.guardedLiveSellAlreadyRunning,
      );
    }
    guardedPositionSellLoading = true;
    guardedPositionSellError = null;
    notifyListeners();
    try {
      final result = await apiClient.syncGuardedPositionSellResult(attemptId);
      latestGuardedPositionSellResult = result;
      return ActionResult(
        success: true,
        message: strings.guardedLiveSellResultSynced(result.resultStatus),
      );
    } catch (e) {
      guardedPositionSellError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(guardedPositionSellError!),
      );
    } finally {
      guardedPositionSellLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshDailyOpsSummary({
    bool silent = false,
  }) async {
    if (dailyOpsSummaryLoading) {
      return ActionResult(
        success: false,
        message: strings.dailyOpsSummaryAlreadyLoading,
      );
    }
    dailyOpsSummaryLoading = true;
    dailyOpsSummaryError = null;
    if (!silent) notifyListeners();
    try {
      dailyOpsSummary = await apiClient.fetchDailyOpsSummary(
        provider: selectedProviderCode,
        market: selectedMarketCode,
      );
      return ActionResult(
        success: true,
        message: strings.dailyOpsSummaryRefreshed(
          dailyOpsSummary!.orderSummary.totalOrdersToday,
        ),
      );
    } catch (e) {
      dailyOpsSummaryError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(dailyOpsSummaryError!),
      );
    } finally {
      dailyOpsSummaryLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshOperatorAlerts({
    bool silent = false,
  }) async {
    if (operatorAlertsLoading) {
      return ActionResult(
        success: false,
        message: strings.operatorAlertsAlreadyLoading,
      );
    }
    operatorAlertsLoading = true;
    operatorAlertsError = null;
    if (!silent) notifyListeners();
    try {
      operatorAlerts = await apiClient.fetchOperatorAlerts(
        provider: selectedProviderCode,
        market: selectedMarketCode,
      );
      return ActionResult(
        success: true,
        message: strings.operatorAlertsRefreshed(
          operatorAlerts!.summary.activeAlertCount,
        ),
      );
    } catch (e) {
      operatorAlertsError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(operatorAlertsError!),
      );
    } finally {
      operatorAlertsLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshStrategyAutoBuyOperations({
    bool silent = false,
  }) async {
    if (strategyAutoBuyOperationsLoading) {
      return const ActionResult(
        success: false,
        message: 'Auto buy operations status is already loading.',
      );
    }
    strategyAutoBuyOperationsLoading = true;
    strategyAutoBuyOperationsError = null;
    if (!silent) notifyListeners();
    try {
      strategyAutoBuyOperationsStatus =
          await apiClient.fetchStrategyAutoBuyOperationsStatus();
      return ActionResult(
        success: true,
        message:
            'Auto buy operations refreshed: ${strategyAutoBuyOperationsStatus!.autoBuyStage}.',
      );
    } catch (e) {
      strategyAutoBuyOperationsError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyAutoBuyOperationsError!),
      );
    } finally {
      strategyAutoBuyOperationsLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshStrategyAutoBuyScheduler({
    bool silent = false,
  }) async {
    if (strategyAutoBuySchedulerLoading) {
      return const ActionResult(
        success: false,
        message: 'Auto buy scheduler status is already loading.',
      );
    }
    strategyAutoBuySchedulerLoading = true;
    strategyAutoBuySchedulerError = null;
    if (!silent) notifyListeners();
    try {
      strategyAutoBuySchedulerStatus =
          await apiClient.fetchStrategyAutoBuySchedulerStatus();
      return ActionResult(
        success: true,
        message:
            'Auto buy scheduler refreshed: ${strategyAutoBuySchedulerStatus!.primaryBlockReason ?? 'ready'}.',
      );
    } catch (e) {
      strategyAutoBuySchedulerError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyAutoBuySchedulerError!),
      );
    } finally {
      strategyAutoBuySchedulerLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runStrategyAutoBuySchedulerDryRunOnce() async {
    if (strategyAutoBuySchedulerLoading) {
      return const ActionResult(
        success: false,
        message: 'Scheduled dry-run auto buy is already running.',
      );
    }
    strategyAutoBuySchedulerLoading = true;
    strategyAutoBuySchedulerError = null;
    notifyListeners();
    try {
      final result = await apiClient.runStrategyAutoBuySchedulerDryRunOnce();
      strategyAutoBuySchedulerRunResult = result;
      final results = await Future.wait<Object>([
        apiClient.fetchStrategyAutoBuySchedulerStatus(),
        apiClient.fetchStrategyAutoBuyPromotions(status: 'all'),
        apiClient.fetchStrategyAutoBuyOperationsStatus(),
      ]);
      strategyAutoBuySchedulerStatus =
          results[0] as StrategyAutoBuySchedulerStatus;
      strategyAutoBuyPromotions =
          (results[1] as StrategyAutoBuyPromotions).items;
      strategyAutoBuyOperationsStatus =
          results[2] as StrategyAutoBuyOperationsStatus;
      return ActionResult(
        success: result.status == 'ok',
        message: result.status == 'ok'
            ? 'Scheduled dry-run completed: ${result.action}.'
            : 'Scheduled dry-run blocked: ${result.blockReason ?? result.status}.',
      );
    } catch (e) {
      strategyAutoBuySchedulerError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyAutoBuySchedulerError!),
      );
    } finally {
      strategyAutoBuySchedulerLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshAutoBuyLivePhase1({
    bool silent = false,
  }) async {
    if (autoBuyLivePhase1Loading) {
      return ActionResult(
        success: false,
        message: strings.autoBuyPhase1AlreadyLoading,
      );
    }
    autoBuyLivePhase1Loading = true;
    autoBuyLivePhase1Error = null;
    if (!silent) notifyListeners();
    try {
      autoBuyLivePhase1Status = await apiClient.fetchAutoBuyLivePhase1Status(
        provider: 'kis',
        market: 'KR',
      );
      return ActionResult(
        success: true,
        message: strings.autoBuyPhase1Refreshed(
          strings.statusLabel(autoBuyLivePhase1Status!.resultStatus),
        ),
      );
    } catch (e) {
      autoBuyLivePhase1Error = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(autoBuyLivePhase1Error!),
      );
    } finally {
      autoBuyLivePhase1Loading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runAutoBuyLivePhase1Once() async {
    if (autoBuyLivePhase1Loading) {
      return ActionResult(
        success: false,
        message: strings.autoBuyPhase1AlreadyLoading,
      );
    }
    autoBuyLivePhase1Loading = true;
    autoBuyLivePhase1Error = null;
    notifyListeners();
    try {
      final result = await apiClient.runAutoBuyLivePhase1Once(
        provider: 'kis',
        market: 'KR',
        triggerSource: 'manual_phase1_test',
        language: appLanguage.code,
        locale: appLanguage.localeCode,
        confirmPhase1Run: true,
      );
      autoBuyLivePhase1Result = result;
      autoBuyLivePhase1Status = result;
      final refreshes = await Future.wait<Object>([
        apiClient.fetchStrategyAutoBuyPromotions(status: 'all'),
        apiClient.fetchStrategyAutoBuyOperationsStatus(),
        apiClient.fetchAutoBuyLivePhase1Status(
          provider: 'kis',
          market: 'KR',
        ),
      ]);
      strategyAutoBuyPromotions =
          (refreshes[0] as StrategyAutoBuyPromotions).items;
      strategyAutoBuyOperationsStatus =
          refreshes[1] as StrategyAutoBuyOperationsStatus;
      autoBuyLivePhase1Status = refreshes[2] as AutoBuyLivePhase1Result;
      return ActionResult(
        success: result.submitted,
        message: result.submitted
            ? strings.autoBuyPhase1Submitted
            : strings.autoBuyPhase1Blocked(
                result.primaryBlockReason ?? result.resultStatus,
              ),
      );
    } catch (e) {
      autoBuyLivePhase1Error = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(autoBuyLivePhase1Error!),
      );
    } finally {
      autoBuyLivePhase1Loading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshAutoSellLivePhase1({
    bool silent = false,
  }) async {
    if (autoSellLivePhase1Loading) {
      return ActionResult(
        success: false,
        message: strings.autoSellPhase1AlreadyLoading,
      );
    }
    autoSellLivePhase1Loading = true;
    autoSellLivePhase1Error = null;
    if (!silent) notifyListeners();
    try {
      autoSellLivePhase1Status = await apiClient.fetchAutoSellLivePhase1Status(
        provider: 'kis',
        market: 'KR',
      );
      return ActionResult(
        success: true,
        message: strings.autoSellPhase1Refreshed(
          strings.statusLabel(autoSellLivePhase1Status!.resultStatus),
        ),
      );
    } catch (e) {
      autoSellLivePhase1Error = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(autoSellLivePhase1Error!),
      );
    } finally {
      autoSellLivePhase1Loading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runAutoSellLivePhase1Once() async {
    if (autoSellLivePhase1Loading) {
      return ActionResult(
        success: false,
        message: strings.autoSellPhase1AlreadyLoading,
      );
    }
    autoSellLivePhase1Loading = true;
    autoSellLivePhase1Error = null;
    notifyListeners();
    try {
      final result = await apiClient.runAutoSellLivePhase1Once(
        provider: 'kis',
        market: 'KR',
        triggerSource: 'manual_phase1_test',
        language: appLanguage.code,
        locale: appLanguage.localeCode,
        confirmPhase1Run: true,
      );
      autoSellLivePhase1Result = result;
      autoSellLivePhase1Status = result;
      final refreshes = await Future.wait<Object>([
        apiClient.fetchAutoExitCandidates(
          provider: 'kis',
          market: 'KR',
          includeDetails: true,
        ),
        apiClient.fetchPositionManagementDryRunLatest(
          provider: 'kis',
          market: 'KR',
        ),
        apiClient.fetchAutoSellLivePhase1Status(
          provider: 'kis',
          market: 'KR',
        ),
      ]);
      autoExitCandidates = refreshes[0] as AutoExitCandidates;
      positionManagementDryRun = refreshes[1] as PositionManagementDryRun;
      autoSellLivePhase1Status = refreshes[2] as AutoSellLivePhase1Result;
      return ActionResult(
        success: result.submitted,
        message: result.submitted
            ? strings.autoSellPhase1Submitted
            : strings.autoSellPhase1Blocked(
                result.primaryBlockReason ?? result.resultStatus,
              ),
      );
    } catch (e) {
      autoSellLivePhase1Error = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(autoSellLivePhase1Error!),
      );
    } finally {
      autoSellLivePhase1Loading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> updateStrategyAutoBuySchedulerEnabled(
    bool enabled,
  ) async {
    if (strategyAutoBuySchedulerLoading) {
      return const ActionResult(
        success: false,
        message: 'Auto buy scheduler status is already loading.',
      );
    }
    final previousStatus = strategyAutoBuySchedulerStatus;
    strategyAutoBuySchedulerStatus = previousStatus?.copyWith(
      enabled: enabled,
      clearPrimaryBlockReason: enabled,
      primaryBlockReason: enabled ? null : 'scheduler_disabled',
    );
    strategyAutoBuySchedulerLoading = true;
    strategyAutoBuySchedulerError = null;
    notifyListeners();

    final payload = {'strategy_auto_buy_scheduler_enabled': enabled};
    try {
      await apiClient.updateOpsSettings(payload);
      strategyAutoBuySchedulerStatus =
          await apiClient.fetchStrategyAutoBuySchedulerStatus();
      _recordSettingsChangeEvent('Strategy Auto Buy Scheduler', payload);
      return ActionResult(
        success: true,
        message:
            'Dry-run scheduler ${enabled ? 'enabled' : 'disabled'} successfully.',
      );
    } catch (e) {
      strategyAutoBuySchedulerStatus = previousStatus;
      strategyAutoBuySchedulerError = ApiErrorFormatter.format(e.toString());
      try {
        strategyAutoBuySchedulerStatus =
            await apiClient.fetchStrategyAutoBuySchedulerStatus();
      } catch (_) {
        // Keep the local rollback state if backend status is unavailable.
      }
      return ActionResult(
        success: false,
        message:
            'Dry-run scheduler update failed: ${_primaryMessage(strategyAutoBuySchedulerError!)}',
      );
    } finally {
      strategyAutoBuySchedulerLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshStrategyAutoBuyPromotions({
    bool silent = false,
  }) async {
    if (strategyAutoBuyPromotionsLoading) {
      return const ActionResult(
        success: false,
        message: 'Auto buy promotions are already loading.',
      );
    }
    strategyAutoBuyPromotionsLoading = true;
    strategyAutoBuyPromotionsError = null;
    if (!silent) notifyListeners();
    try {
      final promotions =
          await apiClient.fetchStrategyAutoBuyPromotions(status: 'all');
      strategyAutoBuyPromotions = promotions.items;
      strategyLiveAutoBuyPreflights = {
        for (final item in promotions.items)
          if (strategyLiveAutoBuyPreflights.containsKey(item.id))
            item.id: strategyLiveAutoBuyPreflights[item.id]!,
      };
      return ActionResult(
        success: true,
        message: 'Promotion queue refreshed: ${promotions.items.length}.',
      );
    } catch (e) {
      strategyAutoBuyPromotionsError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyAutoBuyPromotionsError!),
      );
    } finally {
      strategyAutoBuyPromotionsLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> acknowledgeStrategyAutoBuyPromotion(
    StrategyAutoBuyPromotion promotion,
  ) async {
    try {
      final result =
          await apiClient.acknowledgeStrategyAutoBuyPromotion(promotion.id);
      strategyAutoBuyPromotions = [
        for (final item in strategyAutoBuyPromotions)
          item.id == promotion.id ? result.promotion : item,
      ];
      strategyLiveAutoBuyPreflights = {
        for (final entry in strategyLiveAutoBuyPreflights.entries)
          if (entry.key != promotion.id) entry.key: entry.value,
      };
      await refreshStrategyAutoBuyOperations(silent: true);
      notifyListeners();
      return ActionResult(
        success: true,
        message: 'Promotion acknowledged: ${result.promotion.symbol ?? '-'}.',
      );
    } catch (e) {
      strategyAutoBuyPromotionsError = ApiErrorFormatter.format(e.toString());
      notifyListeners();
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyAutoBuyPromotionsError!),
      );
    }
  }

  Future<ActionResult> markStrategyAutoBuyPromotionReviewed(
    StrategyAutoBuyPromotion promotion,
  ) async {
    try {
      final result =
          await apiClient.markStrategyAutoBuyPromotionReviewed(promotion.id);
      strategyAutoBuyPromotions = [
        for (final item in strategyAutoBuyPromotions)
          item.id == promotion.id ? result.promotion : item,
      ];
      strategyLiveAutoBuyPreflights = {
        for (final entry in strategyLiveAutoBuyPreflights.entries)
          if (entry.key != promotion.id) entry.key: entry.value,
      };
      await refreshStrategyAutoBuyOperations(silent: true);
      notifyListeners();
      return ActionResult(
        success: true,
        message:
            'Promotion marked reviewed: ${result.promotion.symbol ?? '-'}.',
      );
    } catch (e) {
      strategyAutoBuyPromotionsError = ApiErrorFormatter.format(e.toString());
      try {
        final promotions =
            await apiClient.fetchStrategyAutoBuyPromotions(status: 'all');
        strategyAutoBuyPromotions = promotions.items;
      } catch (_) {
        // Keep the explicit action error as the user-facing failure.
      }
      notifyListeners();
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyAutoBuyPromotionsError!),
      );
    }
  }

  Future<ActionResult> dismissStrategyAutoBuyPromotion(
    StrategyAutoBuyPromotion promotion,
  ) async {
    try {
      final result =
          await apiClient.dismissStrategyAutoBuyPromotion(promotion.id);
      strategyAutoBuyPromotions = [
        for (final item in strategyAutoBuyPromotions)
          item.id == promotion.id ? result.promotion : item,
      ];
      strategyLiveAutoBuyPreflights = {
        for (final entry in strategyLiveAutoBuyPreflights.entries)
          if (entry.key != promotion.id) entry.key: entry.value,
      };
      await refreshStrategyAutoBuyOperations(silent: true);
      notifyListeners();
      return ActionResult(
        success: true,
        message: 'Promotion dismissed: ${result.promotion.symbol ?? '-'}.',
      );
    } catch (e) {
      strategyAutoBuyPromotionsError = ApiErrorFormatter.format(e.toString());
      try {
        final promotions =
            await apiClient.fetchStrategyAutoBuyPromotions(status: 'all');
        strategyAutoBuyPromotions = promotions.items;
      } catch (_) {
        // Keep the explicit action error as the user-facing failure.
      }
      notifyListeners();
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyAutoBuyPromotionsError!),
      );
    }
  }

  Future<ActionResult> preflightGuardedLiveAutoBuyForPromotion(
    StrategyAutoBuyPromotion promotion,
  ) async {
    if (strategyLiveAutoBuyPreflightLoading) {
      return ActionResult(
        success: false,
        message: strings.preflightAlreadyRunning,
      );
    }
    strategyLiveAutoBuyPreflightLoading = true;
    strategyLiveAutoBuyPreflightError = null;
    notifyListeners();
    try {
      final result = await apiClient.preflightStrategyLiveAutoBuy(
        promotionId: promotion.id,
        symbol: promotion.symbol,
        sourceDryRunId: promotion.sourceDryRunTradeRunId,
        language: appLanguage.code,
        locale: appLanguage.localeCode,
      );
      strategyLiveAutoBuyPreflights = {
        ...strategyLiveAutoBuyPreflights,
        promotion.id: result,
      };
      return ActionResult(
        success: !result.isBlocked,
        message: strings.preflightCompletedMessage(
          result.preflightStatus,
          result.primaryBlockReason,
        ),
      );
    } catch (e) {
      strategyLiveAutoBuyPreflightError =
          ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyLiveAutoBuyPreflightError!),
      );
    } finally {
      strategyLiveAutoBuyPreflightLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshGuardedLiveAutoBuyResult(
    StrategyLiveAutoBuyResult result,
  ) async {
    if (strategyLiveAutoBuyResultLoading) {
      return ActionResult(
        success: false,
        message: strings.liveBuyResultAlreadyLoading,
      );
    }
    strategyLiveAutoBuyResultLoading = true;
    strategyLiveAutoBuyResultError = null;
    notifyListeners();
    try {
      final refreshed =
          await apiClient.fetchStrategyLiveAutoBuyResult(result.attemptId);
      latestStrategyLiveAutoBuyConversionResult = refreshed;
      return ActionResult(
        success: true,
        message: strings.liveBuyResultRefreshed(
          strings.statusLabel(refreshed.resultStatus),
        ),
      );
    } catch (e) {
      strategyLiveAutoBuyResultError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyLiveAutoBuyResultError!),
      );
    } finally {
      strategyLiveAutoBuyResultLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> syncGuardedLiveAutoBuyResult(
    StrategyLiveAutoBuyResult result,
  ) async {
    if (strategyLiveAutoBuyResultLoading) {
      return ActionResult(
        success: false,
        message: strings.liveBuyResultAlreadyLoading,
      );
    }
    strategyLiveAutoBuyResultLoading = true;
    strategyLiveAutoBuyResultError = null;
    notifyListeners();
    try {
      final synced =
          await apiClient.syncStrategyLiveAutoBuyResult(result.attemptId);
      latestStrategyLiveAutoBuyConversionResult = synced;
      try {
        final promotions =
            await apiClient.fetchStrategyAutoBuyPromotions(status: 'all');
        strategyAutoBuyPromotions = promotions.items;
      } catch (_) {
        // Keep the synced result visible even if the queue refresh fails.
      }
      return ActionResult(
        success: true,
        message: strings.liveBuyResultSynced(
          strings.statusLabel(synced.resultStatus),
        ),
      );
    } catch (e) {
      strategyLiveAutoBuyResultError = ApiErrorFormatter.format(e.toString());
      try {
        latestStrategyLiveAutoBuyConversionResult =
            await apiClient.fetchStrategyLiveAutoBuyResult(result.attemptId);
      } catch (_) {
        // Preserve the sync error as the visible failure.
      }
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyLiveAutoBuyResultError!),
      );
    } finally {
      strategyLiveAutoBuyResultLoading = false;
      notifyListeners();
    }
  }

  void clearGuardedLiveAutoBuyResult() {
    latestStrategyLiveAutoBuyConversionResult = null;
    strategyLiveAutoBuyResultError = null;
    notifyListeners();
  }

  Future<ActionResult> runGuardedLiveAutoBuyForPromotion(
    StrategyAutoBuyPromotion promotion,
  ) async {
    if (!promotion.canRunGuardedLive) {
      final reason = promotion.conversionBlockReason ?? 'promotion_blocked';
      await refreshStrategyAutoBuyPromotions(silent: true);
      return ActionResult(
        success: false,
        message: 'Guarded live auto buy is blocked: $reason.',
      );
    }
    final preflight = strategyLiveAutoBuyPreflights[promotion.id];
    if (preflight != null && !preflight.isAllowed) {
      final reason =
          preflight.primaryBlockReason ?? preflight.nextRequiredAction;
      return ActionResult(
        success: false,
        message: strings.preflightBlocksConversion(reason),
      );
    }
    if (strategyLiveAutoBuyLoading) {
      return const ActionResult(
        success: false,
        message: 'Strategy live auto buy is already running.',
      );
    }
    strategyLiveAutoBuyLoading = true;
    strategyLiveAutoBuyError = null;
    notifyListeners();
    try {
      strategyLiveAutoBuyReadiness =
          await apiClient.fetchStrategyLiveAutoBuyReadiness(
        symbol: promotion.symbol,
        sourceDryRunId: promotion.sourceDryRunTradeRunId,
      );
      if (strategyLiveAutoBuyReadiness?.ready != true) {
        final reason =
            strategyLiveAutoBuyReadiness?.primaryBlockReason ?? 'not_ready';
        final promotions =
            await apiClient.fetchStrategyAutoBuyPromotions(status: 'all');
        strategyAutoBuyPromotions = promotions.items;
        return ActionResult(
          success: false,
          message: 'Guarded live auto buy is blocked: $reason.',
        );
      }
      final requestId =
          'flutter-promotion-auto-buy-${promotion.id}-${DateTime.now().millisecondsSinceEpoch}';
      final result = await apiClient.runStrategyLiveAutoBuyOnce(
        promotionId: promotion.id,
        symbol: promotion.symbol,
        sourceDryRunId: promotion.sourceDryRunTradeRunId,
        triggerSource: 'flutter_promotion_queue',
        clientRequestId: requestId,
      );
      strategyLiveAutoBuyResult = result;
      if (result.attemptId != null) {
        try {
          latestStrategyLiveAutoBuyConversionResult =
              await apiClient.fetchStrategyLiveAutoBuyResult(result.attemptId!);
        } catch (e) {
          strategyLiveAutoBuyResultError =
              ApiErrorFormatter.format(e.toString());
        }
      }
      final results = await Future.wait<Object>([
        apiClient.fetchStrategyAutoBuyPromotions(status: 'all'),
        apiClient.fetchStrategyAutoBuyOperationsStatus(),
        apiClient.fetchStrategyLiveAutoBuyReadiness(),
        apiClient.fetchStrategyLiveAutoBuyRecent(limit: 10),
      ]);
      strategyAutoBuyPromotions =
          (results[0] as StrategyAutoBuyPromotions).items;
      strategyLiveAutoBuyPreflights = {
        for (final item in strategyAutoBuyPromotions)
          if (item.canRunGuardedLive &&
              strategyLiveAutoBuyPreflights.containsKey(item.id))
            item.id: strategyLiveAutoBuyPreflights[item.id]!,
      };
      strategyAutoBuyOperationsStatus =
          results[1] as StrategyAutoBuyOperationsStatus;
      strategyLiveAutoBuyReadiness = results[2] as StrategyLiveAutoBuyReadiness;
      strategyLiveAutoBuyRecent =
          (results[3] as StrategyLiveAutoBuyRecent).items;
      return ActionResult(
        success: result.submitted,
        message: result.submitted
            ? 'Guarded live auto buy submitted: ${result.symbol ?? promotion.symbol ?? '-'}.'
            : 'Guarded live auto buy blocked: ${result.blockReason ?? result.status}.',
      );
    } catch (e) {
      strategyLiveAutoBuyError = ApiErrorFormatter.format(e.toString());
      try {
        final promotions =
            await apiClient.fetchStrategyAutoBuyPromotions(status: 'all');
        strategyAutoBuyPromotions = promotions.items;
      } catch (_) {
        // Preserve the live conversion error as the user-facing failure.
      }
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyLiveAutoBuyError!),
      );
    } finally {
      strategyLiveAutoBuyLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runStrategyLiveAutoExitOnce() async {
    if (strategyLiveAutoExitLoading) {
      return const ActionResult(
        success: false,
        message: 'Strategy live auto exit is already running.',
      );
    }
    if (strategyLiveAutoExitReadiness?.ready != true) {
      final reason =
          strategyLiveAutoExitReadiness?.primaryBlockReason ?? 'not_ready';
      return ActionResult(
        success: false,
        message: 'Guarded live auto exit is blocked: $reason.',
      );
    }
    strategyLiveAutoExitLoading = true;
    strategyLiveAutoExitError = null;
    notifyListeners();
    try {
      final requestId =
          'flutter-live-auto-exit-${DateTime.now().millisecondsSinceEpoch}';
      final result = await apiClient.runStrategyLiveAutoExitOnce(
        symbol: strategyLiveAutoExitReadiness?.selectedSymbol,
        clientRequestId: requestId,
      );
      strategyLiveAutoExitResult = result;
      final results = await Future.wait<Object>([
        apiClient.fetchStrategyLiveAutoExitReadiness(),
        apiClient.fetchStrategyLiveAutoExitRecent(limit: 10),
      ]);
      strategyLiveAutoExitReadiness =
          results[0] as StrategyLiveAutoExitReadiness;
      final recent = results[1] as StrategyLiveAutoExitRecent;
      strategyLiveAutoExitRecent = recent.items;
      final message = result.submitted
          ? 'Guarded live auto exit submitted: ${result.symbol ?? '-'}.'
          : 'Guarded live auto exit blocked: ${result.blockReason ?? result.status}.';
      return ActionResult(
        success: result.submitted,
        message: message,
      );
    } catch (e) {
      strategyLiveAutoExitError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyLiveAutoExitError!),
      );
    } finally {
      strategyLiveAutoExitLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshStrategyLiveAutoExit({
    bool silent = false,
  }) async {
    if (strategyLiveAutoExitLoading) {
      return const ActionResult(
        success: false,
        message: 'Strategy live auto exit status is already loading.',
      );
    }
    strategyLiveAutoExitLoading = true;
    strategyLiveAutoExitError = null;
    if (!silent) notifyListeners();
    try {
      final results = await Future.wait<Object>([
        apiClient.fetchStrategyLiveAutoExitReadiness(),
        apiClient.fetchStrategyLiveAutoExitRecent(limit: 10),
      ]);
      strategyLiveAutoExitReadiness =
          results[0] as StrategyLiveAutoExitReadiness;
      final recent = results[1] as StrategyLiveAutoExitRecent;
      strategyLiveAutoExitRecent = recent.items;
      strategyLiveAutoExitResult = recent.latest;
      return ActionResult(
        success: true,
        message:
            'Guarded live auto exit status refreshed: ${recent.items.length}.',
      );
    } catch (e) {
      strategyLiveAutoExitError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(strategyLiveAutoExitError!),
      );
    } finally {
      strategyLiveAutoExitLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshAgentReviewQueue({String? filter}) async {
    if (filter != null && filter.trim().isNotEmpty) {
      selectedAgentQueueFilter = filter.trim();
    }
    isLoadingAgentReviewQueue = true;
    agentOperationsError = null;
    notifyListeners();
    try {
      agentReviewQueue = await apiClient.fetchAgentReviewQueue(
        queueType: selectedAgentQueueFilter,
        status: 'open',
      );
      return const ActionResult(
        success: true,
        message: 'Agent review queue refreshed.',
      );
    } catch (e) {
      agentOperationsError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(agentOperationsError!),
      );
    } finally {
      isLoadingAgentReviewQueue = false;
      notifyListeners();
    }
  }

  Future<ActionResult> markAgentQueueItemReviewed(String queueKey) async {
    if (queueKey.trim().isEmpty) {
      return const ActionResult(
        success: false,
        message: 'No review queue item selected.',
      );
    }
    try {
      await apiClient.markAgentReviewQueueItemReviewed(
        queueKey,
        reviewerNote: 'Reviewed from Flutter Agent Operations Dashboard.',
      );
      await refreshAgentReviewQueue();
      await refreshAgentOperationsSummary();
      return const ActionResult(
        success: true,
        message: 'Agent queue item marked reviewed.',
      );
    } catch (e) {
      agentOperationsError = ApiErrorFormatter.format(e.toString());
      notifyListeners();
      return ActionResult(
        success: false,
        message: _primaryMessage(agentOperationsError!),
      );
    }
  }

  Future<ActionResult> dismissAgentQueueItem(String queueKey) async {
    if (queueKey.trim().isEmpty) {
      return const ActionResult(
        success: false,
        message: 'No review queue item selected.',
      );
    }
    try {
      await apiClient.dismissAgentReviewQueueItem(
        queueKey,
        reviewerNote: 'Dismissed from Flutter Agent Operations Dashboard.',
      );
      await refreshAgentReviewQueue();
      await refreshAgentOperationsSummary();
      return const ActionResult(
        success: true,
        message: 'Agent queue item dismissed.',
      );
    } catch (e) {
      agentOperationsError = ApiErrorFormatter.format(e.toString());
      notifyListeners();
      return ActionResult(
        success: false,
        message: _primaryMessage(agentOperationsError!),
      );
    }
  }

  Future<ActionResult> openAgentConversationFromQueue(
    String? conversationKey,
  ) async {
    final key = conversationKey?.trim();
    if (key == null || key.isEmpty) {
      return const ActionResult(
        success: false,
        message: 'This review item is not linked to a chat conversation.',
      );
    }
    final result = await loadAgentConversationHistory(key);
    if (result.success) {
      setAgentChatMode(AgentChatPanelMode.expanded);
      return const ActionResult(
        success: true,
        message: 'Agent chat opened for this review item.',
      );
    }
    return result;
  }

  Future<ActionResult> runSafeActionFromQueue(int? planId) async {
    if (planId == null || planId <= 0) {
      return const ActionResult(
        success: false,
        message: 'No agent plan is linked to this queue item.',
      );
    }
    isAgentRunning = true;
    agentOperationsError = null;
    notifyListeners();
    try {
      final run = await apiClient.runAgentPlan(
        planId,
        operatorNote: 'Triggered from Flutter Agent Operations review queue.',
      );
      latestAgentRun = run;
      await refreshAgentOperationsSummary();
      await refreshAgentReviewQueue();
      return ActionResult(
        success: !run.isBlocked,
        message: run.isBlocked
            ? 'Agent safe action blocked. No order submitted.'
            : 'Agent safe action completed. No order submitted.',
      );
    } catch (e) {
      agentOperationsError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(agentOperationsError!),
      );
    } finally {
      isAgentRunning = false;
      notifyListeners();
    }
  }

  Future<ActionResult> prepareTicketFromQueue(int? planId) async {
    if (planId == null || planId <= 0) {
      return const ActionResult(
        success: false,
        message: 'No agent plan is linked to this queue item.',
      );
    }
    isAgentPreparingTicket = true;
    agentOperationsError = null;
    notifyListeners();
    try {
      final prefill = await apiClient.prepareAgentManualTicket(
        planId,
        operatorNote: 'Prepared from Flutter Agent Operations review queue.',
      );
      latestAgentPrefill = prefill;
      final applied = applyAgentPrefillToManualTicket(prefill);
      await refreshAgentOperationsSummary();
      await refreshAgentReviewQueue();
      if (!applied.success) {
        return ActionResult(
          success: false,
          message: prefill.requiresAuth
              ? 'Auth required. No ticket was prepared.'
              : 'Manual ticket prefill blocked. No order submitted.',
        );
      }
      return const ActionResult(
        success: true,
        message:
            'Manual ticket prepared from Agent review queue. Validate and submit manually.',
      );
    } catch (e) {
      agentOperationsError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(agentOperationsError!),
      );
    } finally {
      isAgentPreparingTicket = false;
      notifyListeners();
    }
  }

  Future<void> saveAgentUserMessage(String text) async {
    await _persistAgentMessage(
      role: 'user',
      text: text,
      messageType: 'plain_text',
    );
  }

  Future<void> saveAgentAssistantMessage({
    required String text,
    required String messageType,
    String status = 'completed',
    int? commandLogId,
    int? planId,
    int? planRunId,
    int? authApprovalRequestId,
    int? prefillSourcePlanId,
    String? modelName,
    String? parserStatus,
    Map<String, dynamic>? safety,
    Map<String, dynamic>? metadata,
  }) async {
    await _persistAgentMessage(
      role: 'assistant',
      text: text,
      messageType: messageType,
      status: status,
      commandLogId: commandLogId,
      planId: planId,
      planRunId: planRunId,
      authApprovalRequestId: authApprovalRequestId,
      prefillSourcePlanId: prefillSourcePlanId,
      modelName: modelName,
      parserStatus: parserStatus,
      safety: safety,
      metadata: metadata,
    );
  }

  Future<ActionResult> sendAgentMessage(String text) async {
    final cleanText = text.trim();
    if (cleanText.isEmpty) {
      return ActionResult(
        success: false,
        message: strings.agentEnterMessage,
      );
    }

    await initializeAgentConversation();

    final now = DateTime.now();
    final assistantId = _newAgentMessageId('assistant');
    agentMessages = [
      ...agentMessages,
      AgentChatMessage(
        id: _newAgentMessageId('user'),
        role: AgentChatRole.user,
        text: cleanText,
        createdAt: now,
        status: AgentChatStatus.sent,
      ),
      AgentChatMessage(
        id: assistantId,
        role: AgentChatRole.assistant,
        text: strings.agentParsing,
        createdAt: now,
        status: AgentChatStatus.parsing,
        safetyBadges: [
          strings.serverSideApi,
          strings.safeMode,
          strings.noAutoSubmit,
        ],
      ),
    ];
    isAgentParsing = true;
    isAgentPlanCreating = false;
    agentErrorMessage = null;
    notifyListeners();

    try {
      final chatResponse = await apiClient.sendAgentChatMessage(
        message: cleanText,
        conversationKey: activeAgentConversationKey,
        context: _agentContext(),
        autoCreateConversation: true,
        language: appLanguage.code,
        locale: appLanguage.localeCode,
      );
      _applyAgentChatSendResponse(chatResponse);
      _replaceAgentMessage(
        assistantId,
        _agentMessageForChatSendResponse(assistantId, chatResponse, now),
      );
      isAgentParsing = false;
      isAgentPlanCreating = false;
      notifyListeners();
      return ActionResult(
        success: chatResponse.answer.answerType != 'error',
        message: chatResponse.answer.answerType == 'error'
            ? strings.agentErrorNoOrder
            : strings.agentAnsweredNoOrder,
      );
    } catch (chatSendError) {
      agentHistoryError =
          'Chat send endpoint unavailable; using legacy parse flow. ${ApiErrorFormatter.format(chatSendError.toString())}';
      _replaceAgentMessage(
        assistantId,
        AgentChatMessage(
          id: assistantId,
          role: AgentChatRole.assistant,
          text: strings.chatEndpointFallback,
          createdAt: now,
          status: AgentChatStatus.parsing,
          safetyBadges: ['FALLBACK PARSER', strings.noAutoSubmit],
        ),
      );
      notifyListeners();

      try {
        await saveAgentUserMessage(cleanText);
        final parsed = await apiClient.parseAgentCommand(
          message: cleanText,
          conversationId: _agentConversationKeyForRequests(),
          context: _agentContext(),
        );
        latestAgentCommand = parsed;

        if (parsed.commandLogId == null) {
          _replaceAgentMessage(
            assistantId,
            _agentMessageForParsedCommand(assistantId, parsed),
          );
          await saveAgentAssistantMessage(
            text: parsed.command.userVisibleSummary,
            messageType: 'command_parse',
            commandLogId: parsed.commandLogId,
            modelName: parsed.modelName,
            parserStatus: parsed.parserStatus,
            safety: parsed.safety,
            metadata: _agentCommandMetadata(parsed),
          );
          return const ActionResult(
            success: true,
            message: 'Agent command parsed. No plan was created.',
          );
        }

        _replaceAgentMessage(
          assistantId,
          _agentMessageForParsedCommand(
            assistantId,
            parsed,
            textOverride: 'Command parsed. Creating a plan review...',
          ),
        );
        isAgentParsing = false;
        isAgentPlanCreating = true;
        notifyListeners();

        final planResponse = await apiClient.createAgentPlanFromCommand(
          parsed.commandLogId!,
        );
        latestAgentPlan = planResponse.plan;
        final status = _agentStatusForPlan(planResponse.plan);
        _replaceAgentMessage(
          assistantId,
          AgentChatMessage(
            id: assistantId,
            role: AgentChatRole.assistant,
            text: _agentPlanAssistantText(planResponse.plan),
            createdAt: now,
            status: status,
            commandLogId: parsed.commandLogId,
            planId: planResponse.plan.id,
            prefillAvailable: planResponse.plan.canPrepareManualTicket,
            safetyBadges: _agentSafetyBadges(parsed, planResponse.plan),
            metadata: {
              'parser_status': parsed.parserStatus,
              if (parsed.modelName != null) 'model_name': parsed.modelName,
            },
          ),
        );
        await saveAgentAssistantMessage(
          text: _agentPlanAssistantText(planResponse.plan),
          messageType: 'plan_review',
          commandLogId: parsed.commandLogId,
          planId: planResponse.plan.id,
          modelName: parsed.modelName,
          parserStatus: parsed.parserStatus,
          safety: planResponse.safety,
          metadata: _agentPlanMetadata(parsed, planResponse.plan),
        );
        return const ActionResult(
          success: true,
          message: 'Agent plan created for review. No order submitted.',
        );
      } catch (e) {
        agentErrorMessage = ApiErrorFormatter.format(e.toString());
        _replaceAgentMessage(
          assistantId,
          AgentChatMessage(
            id: assistantId,
            role: AgentChatRole.error,
            text: _primaryMessage(agentErrorMessage!),
            createdAt: now,
            status: AgentChatStatus.failed,
            safetyBadges: const ['NO AUTO SUBMIT'],
          ),
        );
        await saveAgentAssistantMessage(
          text: _primaryMessage(agentErrorMessage!),
          messageType: 'error',
          status: 'failed',
          metadata: const {'message_type': 'error'},
        );
        return ActionResult(
            success: false, message: _primaryMessage(agentErrorMessage!));
      } finally {
        isAgentParsing = false;
        isAgentPlanCreating = false;
        notifyListeners();
      }
    }
  }

  Future<ActionResult> confirmAgentChatLiveOrder(
    AgentChatLiveOrderAction action,
  ) async {
    if (action.actionId <= 0) {
      return const ActionResult(
        success: false,
        message: 'Live order action is missing an action id.',
      );
    }
    if (!action.isPending) {
      return ActionResult(
        success: false,
        message: 'Live order action is ${action.status}.',
      );
    }
    if (_agentLiveOrderActionBusy.contains(action.actionId)) {
      return const ActionResult(
        success: false,
        message: 'Live order action is already being processed.',
      );
    }

    _agentLiveOrderActionBusy.add(action.actionId);
    agentErrorMessage = null;
    notifyListeners();
    try {
      final response = await apiClient.confirmAgentChatLiveOrder(action);
      if (response.liveOrderAction != null) {
        _replaceLiveOrderActionInMessages(response.liveOrderAction!);
      }
      _appendAgentLiveOrderResponseMessage(response);
      final submitted = response.status == 'submitted' ||
          response.answer.answerType == 'live_order_submitted';
      return ActionResult(
        success: submitted,
        message: response.answer.text.isEmpty
            ? submitted
                ? 'Live order submitted.'
                : 'Live order was not submitted.'
            : response.answer.text,
      );
    } catch (e) {
      final message = _primaryMessage(ApiErrorFormatter.format(e.toString()));
      agentErrorMessage = message;
      _appendAgentAssistantMessage(
        message,
        status: AgentChatStatus.failed,
        badges: const ['LIVE ORDER', 'CONFIRM FAILED', 'NO ORDER SUBMITTED'],
        messageType: 'live_order_failed',
        metadata: {
          'answer_type': 'live_order_failed',
          'live_order_action': action.raw,
        },
      );
      return ActionResult(success: false, message: message);
    } finally {
      _agentLiveOrderActionBusy.remove(action.actionId);
      notifyListeners();
    }
  }

  Future<ActionResult> cancelAgentChatLiveOrder(
    AgentChatLiveOrderAction action,
  ) async {
    if (action.actionId <= 0) {
      return const ActionResult(
        success: false,
        message: 'Live order action is missing an action id.',
      );
    }
    if (!action.isPending) {
      return ActionResult(
        success: false,
        message: 'Live order action is ${action.status}.',
      );
    }
    if (_agentLiveOrderActionBusy.contains(action.actionId)) {
      return const ActionResult(
        success: false,
        message: 'Live order action is already being processed.',
      );
    }

    _agentLiveOrderActionBusy.add(action.actionId);
    agentErrorMessage = null;
    notifyListeners();
    try {
      final response =
          await apiClient.cancelAgentChatLiveOrder(action.actionId);
      if (response.liveOrderAction != null) {
        _replaceLiveOrderActionInMessages(response.liveOrderAction!);
      }
      _appendAgentLiveOrderResponseMessage(response);
      final cancelled = response.status == 'cancelled' ||
          response.answer.answerType == 'live_order_cancelled';
      return ActionResult(
        success: cancelled,
        message: response.answer.text.isEmpty
            ? cancelled
                ? 'Live order cancelled.'
                : 'Live order was not cancelled.'
            : response.answer.text,
      );
    } catch (e) {
      final message = _primaryMessage(ApiErrorFormatter.format(e.toString()));
      agentErrorMessage = message;
      _appendAgentAssistantMessage(
        message,
        status: AgentChatStatus.failed,
        badges: const ['LIVE ORDER', 'CANCEL FAILED'],
        messageType: 'live_order_failed',
        metadata: {
          'answer_type': 'live_order_failed',
          'live_order_action': action.raw,
        },
      );
      return ActionResult(success: false, message: message);
    } finally {
      _agentLiveOrderActionBusy.remove(action.actionId);
      notifyListeners();
    }
  }

  Future<ActionResult> confirmAgentChatStrategyAction(
    AgentChatStrategyAction action,
  ) async {
    if (action.actionId <= 0) {
      return const ActionResult(
        success: false,
        message: 'Strategy action is missing an action id.',
      );
    }
    if (!action.isPending) {
      return ActionResult(
        success: false,
        message: 'Strategy action is ${action.status}.',
      );
    }
    if (_agentStrategyActionBusy.contains(action.actionId)) {
      return const ActionResult(
        success: false,
        message: 'Strategy action is already being processed.',
      );
    }

    _agentStrategyActionBusy.add(action.actionId);
    agentErrorMessage = null;
    notifyListeners();
    try {
      final response = await apiClient.confirmAgentChatStrategyAction(action);
      if (response.strategyAction != null) {
        _replaceStrategyActionInMessages(response.strategyAction!);
      }
      if (response.activeProfile != null) {
        activeStrategyProfile = response.activeProfile;
      }
      _appendAgentStrategyActionResponseMessage(response);
      final applied = response.status == 'applied' ||
          response.answer.answerType == 'strategy_profile_applied';
      return ActionResult(
        success: applied,
        message: response.answer.text.isEmpty
            ? applied
                ? 'Strategy profile applied. No order submitted.'
                : 'Strategy profile was not applied.'
            : response.answer.text,
      );
    } catch (e) {
      final message = _primaryMessage(ApiErrorFormatter.format(e.toString()));
      agentErrorMessage = message;
      _appendAgentAssistantMessage(
        message,
        status: AgentChatStatus.failed,
        badges: const ['PROFILE ONLY', 'CONFIRM FAILED', 'NO ORDER SUBMIT'],
        messageType: 'strategy_profile_blocked',
        metadata: {
          'answer_type': 'strategy_profile_blocked',
          'strategy_action': action.raw,
        },
      );
      return ActionResult(success: false, message: message);
    } finally {
      _agentStrategyActionBusy.remove(action.actionId);
      notifyListeners();
    }
  }

  Future<ActionResult> cancelAgentChatStrategyAction(
    AgentChatStrategyAction action,
  ) async {
    if (action.actionId <= 0) {
      return const ActionResult(
        success: false,
        message: 'Strategy action is missing an action id.',
      );
    }
    if (!action.isPending) {
      return ActionResult(
        success: false,
        message: 'Strategy action is ${action.status}.',
      );
    }
    if (_agentStrategyActionBusy.contains(action.actionId)) {
      return const ActionResult(
        success: false,
        message: 'Strategy action is already being processed.',
      );
    }

    _agentStrategyActionBusy.add(action.actionId);
    agentErrorMessage = null;
    notifyListeners();
    try {
      final response =
          await apiClient.cancelAgentChatStrategyAction(action.actionId);
      if (response.strategyAction != null) {
        _replaceStrategyActionInMessages(response.strategyAction!);
      }
      _appendAgentStrategyActionResponseMessage(response);
      final cancelled = response.status == 'cancelled' ||
          response.answer.answerType == 'strategy_profile_cancelled';
      return ActionResult(
        success: cancelled,
        message: response.answer.text.isEmpty
            ? cancelled
                ? 'Strategy profile change cancelled.'
                : 'Strategy profile change was not cancelled.'
            : response.answer.text,
      );
    } catch (e) {
      final message = _primaryMessage(ApiErrorFormatter.format(e.toString()));
      agentErrorMessage = message;
      _appendAgentAssistantMessage(
        message,
        status: AgentChatStatus.failed,
        badges: const ['PROFILE ONLY', 'CANCEL FAILED'],
        messageType: 'strategy_profile_blocked',
        metadata: {
          'answer_type': 'strategy_profile_blocked',
          'strategy_action': action.raw,
        },
      );
      return ActionResult(success: false, message: message);
    } finally {
      _agentStrategyActionBusy.remove(action.actionId);
      notifyListeners();
    }
  }

  Future<ActionResult> syncAgentChatLiveOrder(
    AgentChatLiveOrderAction action,
  ) async {
    if (action.actionId <= 0) {
      return const ActionResult(
        success: false,
        message: 'Live order action is missing an action id.',
      );
    }
    if (_agentLiveOrderActionBusy.contains(action.actionId)) {
      return const ActionResult(
        success: false,
        message: 'Live order action is already being processed.',
      );
    }

    _agentLiveOrderActionBusy.add(action.actionId);
    agentErrorMessage = null;
    notifyListeners();
    try {
      final response = await apiClient.syncAgentChatLiveOrder(action.actionId);
      if (response.liveOrderAction != null) {
        _replaceLiveOrderActionInMessages(response.liveOrderAction!);
      }
      _appendAgentLiveOrderResponseMessage(response);
      final synced = response.answer.answerType == 'live_order_status_synced' ||
          response.status == 'synced';
      return ActionResult(
        success: synced,
        message: response.answer.text.isEmpty
            ? synced
                ? 'Live order status synced.'
                : 'Live order status sync needs review.'
            : response.answer.text,
      );
    } catch (e) {
      final message = _primaryMessage(ApiErrorFormatter.format(e.toString()));
      agentErrorMessage = message;
      _appendAgentAssistantMessage(
        message,
        status: AgentChatStatus.failed,
        badges: const ['LIVE ORDER', 'SYNC FAILED', 'NO ORDER SUBMITTED'],
        messageType: 'live_order_status_sync_failed',
        metadata: {
          'answer_type': 'live_order_status_sync_failed',
          'live_order_action': action.raw,
        },
      );
      return ActionResult(success: false, message: message);
    } finally {
      _agentLiveOrderActionBusy.remove(action.actionId);
      notifyListeners();
    }
  }

  Future<ActionResult> runAgentSafePlan([int? planId]) async {
    final plan = latestAgentPlan;
    final id = planId ?? plan?.id;
    if (id == null || id <= 0 || plan == null) {
      return const ActionResult(
        success: false,
        message: 'No agent plan is ready to run.',
      );
    }
    if (!plan.canRunSafeAction) {
      return const ActionResult(
        success: false,
        message: 'This plan is not eligible for safe chat execution.',
      );
    }

    isAgentRunning = true;
    agentErrorMessage = null;
    notifyListeners();
    try {
      final run = await apiClient.runAgentPlan(
        id,
        operatorNote: 'Triggered by Flutter Agent Chat plan review.',
      );
      latestAgentRun = run;
      _appendAgentAssistantMessage(
        run.isBlocked
            ? 'Safe action was blocked by the backend policy.'
            : 'Safe action completed. No live order was submitted.',
        status: run.isBlocked
            ? AgentChatStatus.blocked
            : AgentChatStatus.safeRunCompleted,
        planId: id,
        runId: run.planRunId,
        badges: const ['SAFE EXECUTION ONLY', 'NO AUTO SUBMIT'],
      );
      await saveAgentAssistantMessage(
        text: run.isBlocked
            ? 'Safe action was blocked by the backend policy.'
            : 'Safe action completed. No live order was submitted.',
        messageType: 'safe_run_result',
        status: run.isBlocked ? 'blocked' : 'completed',
        planId: id,
        planRunId: run.planRunId,
        safety: run.safety,
        metadata: {
          'plan_id': id,
          'plan_run_id': run.planRunId,
          'command_type': run.commandType,
        },
      );
      return ActionResult(
        success: !run.isBlocked,
        message: run.isBlocked
            ? 'Agent safe action blocked. No order submitted.'
            : 'Agent safe action completed. No order submitted.',
      );
    } catch (e) {
      agentErrorMessage = ApiErrorFormatter.format(e.toString());
      _appendAgentAssistantMessage(
        _primaryMessage(agentErrorMessage!),
        status: AgentChatStatus.failed,
        badges: const ['NO AUTO SUBMIT'],
      );
      await saveAgentAssistantMessage(
        text: _primaryMessage(agentErrorMessage!),
        messageType: 'error',
        status: 'failed',
        planId: id,
      );
      return ActionResult(
          success: false, message: _primaryMessage(agentErrorMessage!));
    } finally {
      isAgentRunning = false;
      notifyListeners();
    }
  }

  Future<ActionResult> prepareAgentManualTicket([int? planId]) async {
    final plan = latestAgentPlan;
    final id = planId ?? plan?.id;
    if (id == null || id <= 0 || plan == null) {
      return const ActionResult(
        success: false,
        message: 'No agent plan is ready for manual ticket prefill.',
      );
    }
    if (!plan.canPrepareManualTicket) {
      return const ActionResult(
        success: false,
        message: 'This plan cannot prepare a manual ticket from chat.',
      );
    }

    isAgentPreparingTicket = true;
    agentErrorMessage = null;
    notifyListeners();
    try {
      final prefill = await apiClient.prepareAgentManualTicket(
        id,
        operatorNote: 'Prepared from Flutter Agent Chat.',
      );
      latestAgentPrefill = prefill;
      if (prefill.isReady && prefill.prefill != null) {
        applyAgentPrefillToManualTicket(prefill);
        _appendAgentAssistantMessage(
          'Manual ticket prefill is ready in Trading. Validate and submit manually.',
          status: AgentChatStatus.prefillReady,
          planId: id,
          runId: prefill.planRunId,
          badges: const [
            'PREFILL ONLY',
            'MANUAL VALIDATION REQUIRED',
            'CONFIRM_LIVE MANUAL',
            'NO AUTO SUBMIT',
          ],
        );
        await saveAgentAssistantMessage(
          text:
              'Manual ticket prefill is ready in Trading. Validate and submit manually.',
          messageType: 'manual_prefill_result',
          planId: id,
          planRunId: prefill.planRunId,
          prefillSourcePlanId: prefill.planId,
          safety: prefill.safety,
          metadata: {
            'plan_id': id,
            'plan_run_id': prefill.planRunId,
            'prefill_source_plan_id': prefill.planId,
            'command_type': prefill.commandType,
            'prefill_status': prefill.status,
          },
        );
        return const ActionResult(
          success: true,
          message:
              'Agent prepared a manual ticket. Validate and submit manually.',
        );
      }

      final status = prefill.requiresAuth
          ? AgentChatStatus.authRequired
          : AgentChatStatus.blocked;
      _appendAgentAssistantMessage(
        prefill.requiresAuth
            ? 'Auth is required. Approval flow is not connected to live execution yet.'
            : 'Manual ticket prefill was blocked by backend policy.',
        status: status,
        planId: id,
        runId: prefill.planRunId,
        badges: const ['NO AUTO SUBMIT'],
      );
      await saveAgentAssistantMessage(
        text: prefill.requiresAuth
            ? 'Auth is required. Approval flow is not connected to live execution yet.'
            : 'Manual ticket prefill was blocked by backend policy.',
        messageType: prefill.requiresAuth ? 'auth_required' : 'blocked',
        status: prefill.requiresAuth ? 'blocked' : 'blocked',
        planId: id,
        planRunId: prefill.planRunId,
        safety: prefill.safety,
        metadata: {
          'plan_id': id,
          'plan_run_id': prefill.planRunId,
          'command_type': prefill.commandType,
          'prefill_status': prefill.status,
        },
      );
      return ActionResult(
        success: false,
        message: prefill.requiresAuth
            ? 'Auth required. No ticket was prepared.'
            : 'Manual ticket prefill blocked. No order submitted.',
      );
    } catch (e) {
      agentErrorMessage = ApiErrorFormatter.format(e.toString());
      _appendAgentAssistantMessage(
        _primaryMessage(agentErrorMessage!),
        status: AgentChatStatus.failed,
        badges: const ['NO AUTO SUBMIT'],
      );
      await saveAgentAssistantMessage(
        text: _primaryMessage(agentErrorMessage!),
        messageType: 'error',
        status: 'failed',
        planId: id,
      );
      return ActionResult(
          success: false, message: _primaryMessage(agentErrorMessage!));
    } finally {
      isAgentPreparingTicket = false;
      notifyListeners();
    }
  }

  ActionResult applyAgentPrefillToManualTicket(AgentLivePrefill response) {
    final prefill = response.prefill;
    if (!response.isReady || prefill == null) {
      return const ActionResult(
        success: false,
        message: 'Agent prefill is not ready.',
      );
    }

    final market = prefill.market.trim().toUpperCase();
    final provider = prefill.provider.trim().toLowerCase();
    final symbol = market == 'KR'
        ? normalizeKrSymbol(prefill.symbol)
        : prefill.symbol.trim().toUpperCase();
    if (symbol.isEmpty) {
      return const ActionResult(
        success: false,
        message: 'Agent prefill is missing a symbol.',
      );
    }

    selectedProvider =
        provider == 'kis' ? SelectedProvider.kis : SelectedProvider.alpaca;
    selectedPortfolioMarket =
        market == 'KR' ? PortfolioMarket.kr : PortfolioMarket.us;
    selectedWatchlistMarket = selectedPortfolioMarket;
    selectedOrderMarket = selectedPortfolioMarket;
    orderTicketSymbol = symbol;
    orderTicketSide =
        prefill.side.trim().toLowerCase() == 'sell' ? 'sell' : 'buy';
    final wholeQty =
        prefill.qty ?? _wholeAgentPrefillQuantity(prefill.quantity);
    if (wholeQty != null && wholeQty > 0) {
      orderTicketQty = wholeQty;
      orderTicketQtyInput = wholeQty.toString();
    } else if (parsedOrderTicketQty == null || orderTicketQty < 1) {
      orderTicketQty = 1;
      orderTicketQtyInput = '1';
    }
    orderValidationResult = null;
    orderValidationError = null;
    kisLiveConfirmation = false;
    kisManualOrderError = null;
    kisManualOrderErrorRaw = null;
    orderTicketSourceMetadata = {
      ...prefill.sourceMetadata,
      'source': 'agent_plan',
      'source_type': 'agent_manual_ticket_prefill',
      'source_context': 'agent_manual_prefill',
      'operator_action_source': 'agent_manual_prefill',
      'agent_plan_id': response.planId,
      'command_type': response.commandType,
      'market': market,
      'broker': provider,
      'symbol': symbol,
      'side': orderTicketSide,
      if (wholeQty != null) 'quantity': wholeQty,
      if (prefill.notional != null) 'notional': prefill.notional,
      if (prefill.currency != null) 'currency': prefill.currency,
      'manual_confirm_required': true,
      'requires_user_review': true,
      'requires_user_validation': true,
      'requires_confirm_live': true,
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
      message: 'Agent prepared a manual ticket. Validate and submit manually.',
    );
  }

  void useKrCandidateInOrderTicket(Candidate candidate) {
    final normalizedSymbol = normalizeKrSymbol(candidate.symbol);
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
      'source': 'watchlist_candidate',
      'source_type': 'manual_buy_ticket_prefill',
      'source_context': 'watchlist_analyze_in_trading',
      'symbol': normalizedSymbol,
      'company_name': candidate.name,
      'market': 'KR',
      'broker': 'kis',
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

  ActionResult prepareKisTradingFromWatchlistCandidate(
    Candidate candidate, {
    int? candidateRank,
  }) {
    final normalizedSymbol = normalizeKrSymbol(candidate.symbol);
    if (normalizedSymbol.isEmpty) {
      return const ActionResult(
        success: false,
        message: 'Watchlist candidate is missing a KIS symbol.',
      );
    }

    selectedProvider = SelectedProvider.kis;
    selectedPortfolioMarket = PortfolioMarket.kr;
    selectedWatchlistMarket = PortfolioMarket.kr;
    selectedOrderMarket = PortfolioMarket.kr;
    kisGuardedRunSymbol = normalizedSymbol;
    kisGuardedRunConfirmation = false;
    kisSingleSymbolTradingError = null;
    latestKisSingleSymbolTradingResult = null;
    kisTradingSourceContext = {
      'source': 'watchlist_candidate',
      'source_type': 'click_to_trade_prefill',
      'source_context': 'watchlist_analyze_in_trading',
      'symbol': normalizedSymbol,
      'company_name': candidate.name,
      'market': 'KR',
      'broker': 'kis',
      'side': 'buy',
      'qty': null,
      'confirm_live': false,
      if (candidateRank != null) 'candidate_rank': candidateRank,
      'candidate_score': candidate.finalBuyScore ??
          candidate.finalEntryScore ??
          candidate.entryScore ??
          candidate.score,
      'candidate_reason': _firstNonEmpty([
        candidate.noOrderReason,
        candidate.skipReason,
        candidate.blockReason,
        candidate.reason,
        candidate.note,
      ]),
      'candidate_action_hint': candidate.actionHint,
      'candidate_entry_ready': candidate.entryReady,
      'candidate_block_reason': candidate.blockReason,
      'risk_flags': candidate.riskFlags,
      'gating_notes': candidate.gatingNotes,
      'manual_confirm_required': true,
      'watchlist_click_submits_order': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    };
    notifyListeners();
    return ActionResult(
      success: true,
      message: '$normalizedSymbol prepared in KIS Trading. No order submitted.',
    );
  }

  ActionResult prepareKisManualBuyTicketFromSymbol(
    String symbol, {
    int? gateLevel,
  }) {
    final normalizedSymbol = normalizeKrSymbol(symbol);
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
      'source_context': 'direct_manual_ticket',
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
    final symbol = normalizeKrSymbol(position.symbol);
    final qty = position.qty.floor();
    if (symbol.isEmpty || qty < 1) {
      return const ActionResult(
        success: false,
        message: 'Position is missing a sell symbol or whole-share quantity.',
      );
    }

    selectedProvider = SelectedProvider.kis;
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
      'source_context': 'audit_sell_manual_ticket',
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
          'Manual SELL ticket prepared. Open Trading to validate and submit.',
    );
  }

  Future<ActionResult> prepareKisManualSellFromManagedPosition(
    ManagedPosition position,
  ) async {
    final symbol = normalizeKrSymbol(position.symbol);
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

      selectedProvider = SelectedProvider.kis;
      selectedOrderMarket = PortfolioMarket.kr;
      final preparedSymbol = normalizeKrSymbol(preparation.symbol);
      orderTicketSymbol = preparedSymbol;
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
        'source_context': 'audit_sell_manual_ticket',
        'symbol': preparedSymbol,
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
        ...preparation.sourceMetadata,
      };
      notifyListeners();
      return const ActionResult(
        success: true,
        message:
            'Manual SELL ticket prepared. Open Trading to validate and submit.',
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
    final symbol = normalizeKrSymbol(candidate.symbol);
    final qty = candidate.suggestedQuantityInt;
    if (symbol.isEmpty || qty == null) {
      return const ActionResult(
        success: false,
        message: 'Exit candidate is missing a sell symbol or quantity.',
      );
    }

    selectedProvider = SelectedProvider.kis;
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
          'Manual SELL ticket prepared. Open Trading to validate and submit.',
    );
  }

  ActionResult prepareKisManualSellFromShadowCandidate(
    KisExitShadowCandidate candidate, {
    KisExitShadowDecision? decision,
  }) {
    final symbol = normalizeKrSymbol(candidate.symbol);
    final qty = candidate.suggestedQuantityInt;
    if (symbol.isEmpty || qty == null) {
      return const ActionResult(
        success: false,
        message: 'Shadow candidate is missing a sell symbol or quantity.',
      );
    }

    selectedProvider = SelectedProvider.kis;
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
          'Manual SELL ticket prepared. Open Trading to validate and submit.',
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
        message: 'KR top 50 watchlist update already in progress.',
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
        message: 'KR top 50 watchlist updated.',
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

  Future<OrderValidationResult?> validateKisLiveOrderDraft({
    required String symbol,
    required String side,
    required int qty,
    Map<String, dynamic>? sourceMetadata,
  }) async {
    if (orderValidationLoading) return null;
    orderValidationLoading = true;
    orderValidationError = null;
    notifyListeners();
    try {
      await refreshKisSafetyStatus(silent: true);
      return await apiClient.validateKisOrder(
        symbol: symbol,
        side: side,
        qty: qty,
        sourceMetadata: sourceMetadata,
      );
    } catch (e) {
      orderValidationError = ApiErrorFormatter.format(e.toString());
      return null;
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

  Future<ActionResult> refreshKisPositionManagement() async {
    if (kisManagedPositionsLoading || kisLimitedAutoSellLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS position management already in progress.',
      );
    }

    kisManagedPositionsLoading = true;
    kisLimitedAutoSellLoading = true;
    kisManagedPositionsError = null;
    kisLimitedAutoSellError = null;
    notifyListeners();
    try {
      kisManagedPositions = await apiClient.fetchKisManagedPositions();
      latestKisLimitedAutoSellResult =
          await apiClient.fetchKisLimitedAutoSellStatus();
      return ActionResult(
        success: true,
        message:
            'KIS position management refreshed: ${kisManagedPositions.length} holdings.',
      );
    } catch (e) {
      final formatted = ApiErrorFormatter.format(e.toString());
      kisManagedPositionsError =
          'KIS position management unavailable: $formatted';
      return ActionResult(
        success: false,
        message: _primaryMessage(kisManagedPositionsError!),
      );
    } finally {
      kisManagedPositionsLoading = false;
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
      requestedAction: 'analyze_then_maybe_buy',
    );
  }

  Future<ActionResult> runKisSingleSymbolAnalyzeBuy({
    required String symbol,
    int? quantity,
    required int gateLevel,
    required bool confirmLive,
    String requestedAction = 'analyze_then_maybe_buy',
    bool? dryRun,
    Map<String, dynamic>? sourceContext,
  }) async {
    if (kisSingleSymbolTradingLoading) {
      return const ActionResult(
        success: false,
        message: 'Single Symbol Analyze & Buy already in progress.',
      );
    }

    final normalizedSymbol = normalizeKrSymbol(symbol);
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
        requestedAction: requestedAction,
        dryRun: dryRun,
        sourceContext: sourceContext ?? kisTradingSourceContext,
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
        message: 'Single Symbol Analyze & Buy completed: $resultText.',
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

  Future<ActionResult> refreshOpsProductionReadiness({
    bool silent = false,
  }) async {
    if (opsProductionReadinessLoading) {
      return ActionResult(
        success: false,
        message: strings.productionReadinessRefreshInProgress,
      );
    }

    opsProductionReadinessLoading = true;
    opsProductionReadinessError = null;
    if (!silent) notifyListeners();
    try {
      final result = await apiClient.fetchOpsProductionReadiness(
        provider: selectedProviderCode,
        market: selectedMarketCode,
      );
      latestOpsProductionReadiness = result;
      return ActionResult(
        success: true,
        message: strings.productionReadinessStatus(
          strings.readinessStatusLabel(result.overallStatus),
        ),
      );
    } catch (e) {
      opsProductionReadinessError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(opsProductionReadinessError!),
      );
    } finally {
      opsProductionReadinessLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisSchedulerGuardedBuyStatus() async {
    if (kisSchedulerGuardedBuyLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS scheduler guarded buy already in progress.',
      );
    }

    kisSchedulerGuardedBuyLoading = true;
    kisSchedulerGuardedBuyError = null;
    notifyListeners();
    try {
      final result = await apiClient.fetchKisSchedulerGuardedBuyStatus();
      latestKisSchedulerGuardedBuyResult = result;
      return ActionResult(
        success: true,
        message:
            'KIS scheduler guarded buy status refreshed: ${result.reason}.',
      );
    } catch (e) {
      kisSchedulerGuardedBuyError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerGuardedBuyError!),
      );
    } finally {
      kisSchedulerGuardedBuyLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> runKisSchedulerGuardedBuyOnce() async {
    if (kisSchedulerGuardedBuyLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS scheduler guarded buy already in progress.',
      );
    }

    kisSchedulerGuardedBuyLoading = true;
    kisSchedulerGuardedBuyError = null;
    notifyListeners();
    try {
      final result = await apiClient.runKisSchedulerGuardedBuyOnce();
      latestKisSchedulerGuardedBuyResult = result;
      recentRuns = await apiClient.getRecentTradingRuns();
      await refreshKisSchedulerStatus(silent: true);
      if (result.realOrderSubmitted || result.orderId != null) {
        await refreshKisOrderMonitoring(silent: true);
      }
      return ActionResult(
        success: true,
        message: 'KIS scheduler guarded buy completed: ${result.reason}.',
      );
    } catch (e) {
      kisSchedulerGuardedBuyError = ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerGuardedBuyError!),
      );
    } finally {
      kisSchedulerGuardedBuyLoading = false;
      notifyListeners();
    }
  }

  Future<ActionResult> refreshKisSchedulerGuardedSellReview({
    bool silent = false,
  }) async {
    if (kisSchedulerGuardedSellReviewLoading) {
      return const ActionResult(
        success: false,
        message: 'KIS scheduler guarded sell review already in progress.',
      );
    }

    kisSchedulerGuardedSellReviewLoading = true;
    kisSchedulerGuardedSellReviewError = null;
    if (!silent) notifyListeners();
    try {
      final result = await apiClient.fetchKisSchedulerGuardedSellReview();
      latestKisSchedulerGuardedSellReview = result;
      return ActionResult(
        success: true,
        message:
            'KIS scheduler guarded sell review refreshed: ${result.summary.totalAttempts} attempts.',
      );
    } catch (e) {
      kisSchedulerGuardedSellReviewError =
          ApiErrorFormatter.format(e.toString());
      return ActionResult(
        success: false,
        message: _primaryMessage(kisSchedulerGuardedSellReviewError!),
      );
    } finally {
      kisSchedulerGuardedSellReviewLoading = false;
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
      krPortfolioUnavailable = krPortfolioSummary.hasUnavailableKisData;
      krPortfolioError = krPortfolioUnavailable
          ? krPortfolioSummary.kisAuthErrorMessage ??
              'KIS account data partially unavailable'
          : null;
      if (krPortfolioSummary.positionsUnavailable) {
        kisManagedPositions = const [];
        kisManagedPositionsError = null;
      } else {
        await _refreshKisManagedPositions();
      }
    } catch (_) {
      krPortfolioSummary = PortfolioSummary.empty(
        currency: 'KRW',
        cashKnown: false,
        balanceUnavailable: true,
        positionsUnavailable: true,
        openOrdersUnavailable: true,
        kisAuthErrorMessage: 'KIS account data unavailable',
      );
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

  void _rebuildPortfolioManagementItems() {
    final items = <PortfolioPositionManagementItem>[
      ..._buildPortfolioManagementItemsFor(usPortfolioSummary, isKr: false),
      ..._buildPortfolioManagementItemsFor(krPortfolioSummary, isKr: true),
    ]..sort(PortfolioPositionManagementItem.comparePriority);
    portfolioManagementItems = items;
  }

  List<PortfolioPositionManagementItem> _buildPortfolioManagementItemsFor(
    PortfolioSummary summary, {
    required bool isKr,
  }) {
    return [
      for (final position in summary.positions)
        PortfolioPositionManagementItem.fromPosition(
          position: position,
          managedPosition:
              isKr ? kisManagedPositionForSymbol(position.symbol) : null,
          isKr: isKr,
          events: automationRuntimeMonitor?.events ?? const [],
          orders: automationRecentOrders,
        ),
    ];
  }

  void _rebuildAutomationRuntimeMonitorFromCurrentState() {
    automationRuntimeMonitor = AutomationRuntimeMonitor.fromSources(
      settings: settings,
      schedulerStatus: schedulerStatus,
      selectedProvider: selectedBrokerLabel,
      currentLocalTime: _localTimestampNow(),
      lastRefreshTime:
          automationRuntimeMonitor?.global.lastRefreshTime ?? 'Not refreshed',
      kisSchedulerStatus: kisSchedulerStatus,
      guardedSell: latestKisSchedulerGuardedSellResult,
      guardedBuy: latestKisSchedulerGuardedBuyResult,
      runs: automationRecentRuns,
      orders: automationRecentOrders,
      signals: automationRecentSignals,
      localEvents: localAutomationEvents,
      warnings: automationRuntimeMonitor?.warnings ?? const [],
    );
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

    if (validation.isValidationExpired) {
      return 'Validation expired, validate again.';
    }
    if (!validation.effectiveSubmitAllowed) {
      if (validation.message?.isNotEmpty == true) return validation.message!;
      if (validation.gatingNotes.isNotEmpty) {
        return 'Live submit blocked: ${validation.gatingNotes.first}';
      }
      if (validation.blockReasons.isNotEmpty) {
        return 'Live submit blocked: ${validation.blockReasons.first}';
      }
      return 'Live submit blocked by validation summary.';
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

  Map<String, dynamic> _agentContext() {
    return {
      'default_market': selectedMarketCode,
      'default_provider': selectedProviderCode,
      'timezone': 'Asia/Seoul',
      'source': 'flutter_dashboard_agent_chat',
      'conversation_key': _agentConversationKeyForRequests(),
    };
  }

  String _agentConversationKeyForRequests() {
    final key = activeAgentConversationKey?.trim();
    if (key != null && key.isNotEmpty) return key;
    return agentConversationId;
  }

  Future<void> _persistAgentMessage({
    required String role,
    required String text,
    required String messageType,
    String status = 'completed',
    int? commandLogId,
    int? planId,
    int? planRunId,
    int? authApprovalRequestId,
    int? prefillSourcePlanId,
    String? modelName,
    String? parserStatus,
    Map<String, dynamic>? safety,
    Map<String, dynamic>? metadata,
  }) async {
    final key = activeAgentConversationKey;
    if (key == null || key.isEmpty || key == agentConversationId) return;
    isSavingAgentMessage = true;
    notifyListeners();
    try {
      await apiClient.appendAgentChatMessage(
        conversationKey: key,
        role: role,
        text: text,
        messageType: messageType,
        status: status,
        commandLogId: commandLogId,
        planId: planId,
        planRunId: planRunId,
        authApprovalRequestId: authApprovalRequestId,
        prefillSourcePlanId: prefillSourcePlanId,
        modelName: modelName,
        parserStatus: parserStatus,
        safety: safety,
        metadata: metadata,
      );
      agentHistoryError = null;
    } catch (e) {
      agentHistoryError =
          'Saved locally only; history sync failed. ${ApiErrorFormatter.format(e.toString())}';
    } finally {
      isSavingAgentMessage = false;
      notifyListeners();
    }
  }

  Map<String, dynamic> _agentCommandMetadata(AgentCommandParseResult parsed) {
    return {
      if (parsed.commandLogId != null) 'command_log_id': parsed.commandLogId,
      'command_type': parsed.command.commandType,
      'domain': parsed.command.domain,
      'market': parsed.command.market,
      'provider': parsed.command.provider,
      if (parsed.command.symbol != null) 'symbol': parsed.command.symbol,
      'side': parsed.command.side,
      'risk_level': parsed.command.riskLevel,
      'parser_status': parsed.parserStatus,
      if (parsed.modelName != null) 'model_name': parsed.modelName,
      'fallback_used': parsed.fallbackUsed,
    };
  }

  Map<String, dynamic> _agentPlanMetadata(
    AgentCommandParseResult parsed,
    AgentPlan plan,
  ) {
    return {
      ..._agentCommandMetadata(parsed),
      'plan_id': plan.id,
      'scope_hash': plan.scopeHash,
      'command_type': plan.commandType,
      'domain': plan.domain,
      'market': plan.market,
      'provider': plan.provider,
      if (plan.symbol != null) 'symbol': plan.symbol,
      'side': plan.side,
      'risk_level': plan.riskLevel,
      'status': plan.status,
    };
  }

  void _applyAgentChatSendResponse(AgentChatSendResponse response) {
    activeAgentConversationKey = response.conversationKey;
    latestAgentCommand = null;
    latestAgentPlan = response.plan;
    latestAgentRun = response.run;
    if (response.answer.answerType != 'error') {
      agentErrorMessage = null;
    }
    agentHistoryError = null;
  }

  AgentChatMessage _agentMessageForChatSendResponse(
    String id,
    AgentChatSendResponse response,
    DateTime createdAt,
  ) {
    return AgentChatMessage(
      id: id,
      role: response.answer.answerType == 'error'
          ? AgentChatRole.error
          : AgentChatRole.assistant,
      text: response.answer.text,
      createdAt: createdAt,
      status: _agentStatusForChatSendResponse(response),
      conversationKey: response.conversationKey,
      messageType: response.answer.answerType,
      planId: response.plan?.id,
      runId: response.run?.planRunId,
      modelName: response.intent.modelName,
      parserStatus: response.intent.parserStatus,
      prefillAvailable:
          response.availableActions.contains('prepare_manual_ticket'),
      safetyBadges: _agentSafetyBadgesForChatSendResponse(response),
      metadata: _agentMetadataForChatSendResponse(response),
    );
  }

  AgentChatStatus _agentStatusForChatSendResponse(
    AgentChatSendResponse response,
  ) {
    switch (response.answer.answerType) {
      case 'error':
        return AgentChatStatus.failed;
      case 'auth_required':
        return AgentChatStatus.authRequired;
      case 'blocked':
      case 'unsupported':
        return AgentChatStatus.blocked;
      case 'manual_ticket_prepared':
        return response.plan == null
            ? AgentChatStatus.sent
            : AgentChatStatus.readyForReview;
      case 'live_order_confirmation_required':
        return AgentChatStatus.readyForReview;
      case 'strategy_profile_change_confirmation_required':
        return AgentChatStatus.readyForReview;
      case 'live_order_blocked':
      case 'live_order_expired':
      case 'strategy_profile_blocked':
      case 'strategy_profile_expired':
        return AgentChatStatus.blocked;
      case 'live_order_submitted':
      case 'live_order_cancelled':
      case 'strategy_profile_applied':
      case 'strategy_profile_cancelled':
      case 'strategy_profile_answer':
        return AgentChatStatus.sent;
      case 'analysis_summary':
        if (response.run != null) return AgentChatStatus.safeRunCompleted;
        return response.plan == null
            ? AgentChatStatus.sent
            : AgentChatStatus.readyForReview;
      default:
        return AgentChatStatus.sent;
    }
  }

  List<String> _agentSafetyBadgesForChatSendResponse(
    AgentChatSendResponse response,
  ) {
    final labels = strings;
    final isLiveOrderAction = response.liveOrderAction != null ||
        response.answer.answerType == 'live_order_confirmation_required';
    final isStrategyAction = response.strategyAction != null ||
        response.answer.answerType ==
            'strategy_profile_change_confirmation_required';
    final badges = <String>[
      response.intent.fallbackUsed ? labels.fallbackRouter : labels.gptBacked,
      labels.serverSideApi,
    ];
    if (isLiveOrderAction) {
      badges.addAll([
        labels.liveOrder,
        labels.confirmRequired,
        labels.validationRequired,
        labels.riskGated,
        labels.noAutoSubmit,
      ]);
    } else if (isStrategyAction) {
      badges.addAll([
        labels.profileOnly,
        labels.confirmRequired,
        labels.noOrderSubmit,
        labels.strategyTarget,
        response.strategyAction?.requestedProfile.toUpperCase() ?? '',
      ]);
    } else {
      badges.addAll([labels.noOrder, labels.noAutoSubmit]);
    }
    final provider =
        response.liveOrderAction?.provider ?? response.intent.provider;
    final normalizedProvider = provider?.trim().toLowerCase();
    if (provider != null &&
        provider.isNotEmpty &&
        normalizedProvider != 'unknown') {
      badges.add(labels.brokerName(provider));
    }
    if (response.safety.readOnly || response.intent.isReadOnly) {
      badges.add(labels.readOnly);
    }
    if (response.safety.safeExecutionOnly) {
      badges.add(labels.safeAnalysis);
    }
    if (!isLiveOrderAction && !response.safety.validationCalled) {
      badges.add(labels.noValidation);
    }
    if (!response.safety.settingChanged) badges.add(labels.noSettingsChange);
    if (response.availableActions.contains('prepare_manual_ticket')) {
      badges.addAll([
        labels.prefillOnly,
        labels.manualReviewOnly,
        labels.manualValidationRequired,
        labels.confirmLiveManual,
      ]);
    }
    if (response.intent.requiresAuth ||
        response.answer.answerType == 'auth_required') {
      badges.add(labels.authRequired);
    }
    if (response.answer.answerType == 'blocked') badges.add(labels.blocked);
    return badges.where((badge) => badge.trim().isNotEmpty).toSet().toList();
  }

  Map<String, dynamic> _agentMetadataForChatSendResponse(
    AgentChatSendResponse response,
  ) {
    return {
      'intent_category': response.intent.category,
      'answer_type': response.answer.answerType,
      'market': response.intent.market,
      'provider': response.intent.provider,
      if (response.intent.symbol != null) 'symbol': response.intent.symbol,
      'side': response.intent.side,
      if (response.plan != null) 'plan_id': response.plan!.id,
      if (response.run != null) 'plan_run_id': response.run!.planRunId,
      'parser_status': response.intent.parserStatus,
      if (response.intent.modelName != null)
        'model_name': response.intent.modelName,
      'fallback_used': response.intent.fallbackUsed,
      'available_actions': response.availableActions,
      if (response.liveOrderAction != null)
        'live_order_action': response.liveOrderAction!.raw,
      if (response.strategyAction != null)
        'strategy_action': response.strategyAction!.raw,
      'safety': response.safety.raw,
      'context_snapshot': response.contextSnapshot,
      'selected_tools': [
        for (final tool in response.selectedTools)
          {
            'tool_name': tool.toolName,
            'arguments': tool.arguments,
            if (tool.reason != null) 'reason': tool.reason,
          },
      ],
      'tool_results': [
        for (final result in response.toolResults)
          {
            'tool_name': result.toolName,
            'status': result.status,
            'result_type': result.resultType,
            'data': result.data,
            'summary': result.summary,
            if (result.errorMessage != null)
              'error_message': result.errorMessage,
            'safety': result.safety.raw,
          },
      ],
      'result_cards': [
        for (final card in response.resultCards)
          {
            'card_type': card.cardType,
            'title': card.title,
            if (card.subtitle != null) 'subtitle': card.subtitle,
            if (card.primaryValue != null) 'primary_value': card.primaryValue,
            'badges': card.badges,
            'rows': card.rows,
            'data': card.data,
          },
      ],
      'follow_up_suggestions': response.followUpSuggestions,
      'diagnostics': response.diagnostics,
    };
  }

  void _appendAgentLiveOrderResponseMessage(
    AgentChatLiveOrderResponse response,
  ) {
    final action = response.liveOrderAction;
    agentMessages = [
      ...agentMessages,
      AgentChatMessage(
        id: _newAgentMessageId('assistant'),
        role: response.answer.answerType == 'error'
            ? AgentChatRole.error
            : AgentChatRole.assistant,
        text: response.answer.text,
        createdAt: DateTime.now(),
        status: _agentStatusForLiveOrderResponse(response),
        conversationKey: activeAgentConversationKey,
        messageType: response.answer.answerType,
        safetyBadges: _agentSafetyBadgesForLiveOrderResponse(response),
        metadata: {
          'answer_type': response.answer.answerType,
          'live_order_result': {
            'status': response.status,
            if (response.order != null) 'order': response.order,
            if (response.assistantMessageId != null)
              'assistant_message_id': response.assistantMessageId,
            'diagnostics': response.diagnostics,
          },
          if (action != null) 'live_order_action': action.raw,
          'safety': response.safety,
        },
      ),
    ];
  }

  void _appendAgentStrategyActionResponseMessage(
    AgentChatStrategyActionResponse response,
  ) {
    final action = response.strategyAction;
    agentMessages = [
      ...agentMessages,
      AgentChatMessage(
        id: _newAgentMessageId('assistant'),
        role: response.answer.answerType == 'error'
            ? AgentChatRole.error
            : AgentChatRole.assistant,
        text: response.answer.text,
        createdAt: DateTime.now(),
        status: _agentStatusForStrategyActionResponse(response),
        conversationKey: activeAgentConversationKey,
        messageType: response.answer.answerType,
        safetyBadges: _agentSafetyBadgesForStrategyActionResponse(response),
        metadata: {
          'answer_type': response.answer.answerType,
          'strategy_action_result': {
            'status': response.status,
            if (response.assistantMessageId != null)
              'assistant_message_id': response.assistantMessageId,
            'diagnostics': response.diagnostics,
          },
          if (action != null) 'strategy_action': action.raw,
          if (response.activeProfile != null)
            'active_profile': response.activeProfile!.toJson(),
          'safety': response.safety,
        },
      ),
    ];
  }

  AgentChatStatus _agentStatusForLiveOrderResponse(
    AgentChatLiveOrderResponse response,
  ) {
    switch (response.answer.answerType) {
      case 'live_order_blocked':
      case 'live_order_expired':
      case 'live_order_status_sync_failed':
        return AgentChatStatus.blocked;
      case 'error':
        return AgentChatStatus.failed;
      default:
        return AgentChatStatus.sent;
    }
  }

  List<String> _agentSafetyBadgesForLiveOrderResponse(
    AgentChatLiveOrderResponse response,
  ) {
    final safety = response.safety;
    final status = response.status.toUpperCase().replaceAll('_', ' ');
    final badges = <String>[
      'LIVE ORDER',
      if (status.isNotEmpty) status,
      'SERVER-SIDE API',
    ];
    if (safety['real_order_submitted'] == true) {
      badges.add('REAL ORDER');
    } else {
      badges.add('NO ORDER SUBMITTED');
    }
    if (response.answer.answerType == 'live_order_status_synced') {
      badges.add('SYNCED');
    }
    if (safety['validation_called'] == true) badges.add('VALIDATED');
    if (safety['risk_approved'] == true) {
      badges.add('RISK APPROVED');
    } else {
      badges.add('RISK GATED');
    }
    if (safety['manual_submit_called'] == true) badges.add('MANUAL SERVICE');
    if (safety['broker_submit_called'] == true) badges.add('BROKER SUBMIT');
    return badges.toSet().toList();
  }

  AgentChatStatus _agentStatusForStrategyActionResponse(
    AgentChatStrategyActionResponse response,
  ) {
    switch (response.answer.answerType) {
      case 'strategy_profile_blocked':
      case 'strategy_profile_expired':
        return AgentChatStatus.blocked;
      case 'error':
        return AgentChatStatus.failed;
      default:
        return AgentChatStatus.sent;
    }
  }

  List<String> _agentSafetyBadgesForStrategyActionResponse(
    AgentChatStrategyActionResponse response,
  ) {
    final safety = response.safety;
    final status = response.status.toUpperCase().replaceAll('_', ' ');
    final profile =
        response.strategyAction?.requestedProfile.toUpperCase() ?? '';
    final badges = <String>[
      'PROFILE ONLY',
      if (status.isNotEmpty) status,
      if (profile.isNotEmpty) profile,
      'SERVER-SIDE API',
      'NO ORDER SUBMIT',
    ];
    if (safety['setting_changed'] == true) {
      badges.add('STRATEGY APPLIED');
    } else {
      badges.add('NO SETTINGS CHANGE');
    }
    if (safety['validation_called'] != true) badges.add('NO VALIDATION');
    if (safety['scheduler_changed'] != true) badges.add('NO SCHEDULER CHANGE');
    return badges.where((badge) => badge.trim().isNotEmpty).toSet().toList();
  }

  void _replaceLiveOrderActionInMessages(AgentChatLiveOrderAction action) {
    final replacement = action.raw.isEmpty
        ? _liveOrderActionMetadata(action)
        : Map<String, dynamic>.from(action.raw);
    agentMessages = [
      for (final message in agentMessages)
        if (message.liveOrderAction?.actionId == action.actionId)
          message.copyWith(
            metadata: {
              ...message.metadata,
              'live_order_action': replacement,
            },
          )
        else
          message,
    ];
  }

  void _replaceStrategyActionInMessages(AgentChatStrategyAction action) {
    final replacement = action.raw.isEmpty
        ? _strategyActionMetadata(action)
        : Map<String, dynamic>.from(action.raw);
    agentMessages = [
      for (final message in agentMessages)
        if (message.strategyAction?.actionId == action.actionId)
          message.copyWith(
            metadata: {
              ...message.metadata,
              'strategy_action': replacement,
            },
          )
        else
          message,
    ];
  }

  Map<String, dynamic> _strategyActionMetadata(
    AgentChatStrategyAction action,
  ) {
    return {
      'action_id': action.actionId,
      'status': action.status,
      'action_type': action.actionType,
      'requested_profile': action.requestedProfile,
      if (action.currentProfile != null)
        'current_profile': action.currentProfile,
      if (action.expiresAt != null) 'expires_at': action.expiresAt,
      if (action.confirmedAt != null) 'confirmed_at': action.confirmedAt,
      if (action.cancelledAt != null) 'cancelled_at': action.cancelledAt,
      if (action.requestedProfilePayload != null)
        'requested_profile_payload': action.requestedProfilePayload!.toJson(),
      if (action.activeProfile != null)
        'active_profile': action.activeProfile!.toJson(),
      'safety': action.safety,
    };
  }

  Map<String, dynamic> _liveOrderActionMetadata(
    AgentChatLiveOrderAction action,
  ) {
    return {
      'action_id': action.actionId,
      'status': action.status,
      'action_type': action.actionType,
      'provider': action.provider,
      'market': action.market,
      'symbol': action.symbol,
      if (action.symbolName != null) 'symbol_name': action.symbolName,
      'side': action.side,
      'order_type': action.orderType,
      if (action.quantity != null) 'quantity': action.quantity,
      if (action.notionalAmount != null)
        'notional_amount': action.notionalAmount,
      'currency': action.currency,
      if (action.estimatedPrice != null)
        'estimated_price': action.estimatedPrice,
      if (action.estimatedNotional != null)
        'estimated_notional': action.estimatedNotional,
      if (action.expiresAt != null) 'expires_at': action.expiresAt,
      if (action.confirmationPhrase != null)
        'confirmation_phrase': action.confirmationPhrase,
      if (action.confirmationToken != null)
        'confirmation_token': action.confirmationToken,
      if (action.relatedOrderId != null)
        'related_order_id': action.relatedOrderId,
      if (action.brokerOrderId != null) 'broker_order_id': action.brokerOrderId,
      if (action.brokerStatus != null) 'broker_status': action.brokerStatus,
      if (action.internalStatus != null)
        'internal_status': action.internalStatus,
      if (action.lastSyncAt != null) 'last_sync_at': action.lastSyncAt,
      'last_sync_payload': action.lastSyncPayload,
      'audit': action.audit,
      'safety': action.safety,
      'safety_controls': action.safetyControls,
    };
  }

  AgentChatMessage _agentMessageForParsedCommand(
    String id,
    AgentCommandParseResult parsed, {
    String? textOverride,
  }) {
    return AgentChatMessage(
      id: id,
      role: AgentChatRole.assistant,
      text: textOverride ?? parsed.command.userVisibleSummary,
      createdAt: DateTime.now(),
      status: parsed.command.needsClarification
          ? AgentChatStatus.blocked
          : AgentChatStatus.sent,
      commandLogId: parsed.commandLogId,
      safetyBadges: _agentSafetyBadges(parsed, null),
      metadata: {
        'parser_status': parsed.parserStatus,
        if (parsed.modelName != null) 'model_name': parsed.modelName,
      },
    );
  }

  void _replaceAgentMessage(String id, AgentChatMessage replacement) {
    agentMessages = [
      for (final message in agentMessages)
        if (message.id == id) replacement else message,
    ];
  }

  void _appendAgentAssistantMessage(
    String text, {
    required AgentChatStatus status,
    int? planId,
    int? runId,
    List<String> badges = const [],
    String messageType = 'plain_text',
    Map<String, dynamic> metadata = const {},
  }) {
    agentMessages = [
      ...agentMessages,
      AgentChatMessage(
        id: _newAgentMessageId('assistant'),
        role: status == AgentChatStatus.failed
            ? AgentChatRole.error
            : AgentChatRole.assistant,
        text: text,
        createdAt: DateTime.now(),
        status: status,
        conversationKey: activeAgentConversationKey,
        messageType: messageType,
        planId: planId,
        runId: runId,
        safetyBadges: badges,
        metadata: metadata,
      ),
    ];
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

String _newAgentMessageId(String prefix) {
  return '$prefix-${DateTime.now().microsecondsSinceEpoch}';
}

bool _containsOnlyDefaultAgentSafetyMessage(List<AgentChatMessage> messages) {
  return messages.length == 1 && messages.first.role == AgentChatRole.safety;
}

List<AgentChatMessage> _defaultAgentSafetyMessages(AppLanguage language) {
  final strings = AppStrings(language);
  return [
    AgentChatMessage(
      id: _newAgentMessageId('safety'),
      role: AgentChatRole.safety,
      text: strings.agentSafetyIntro,
      createdAt: DateTime.now(),
      status: AgentChatStatus.sent,
      safetyBadges: [
        strings.serverSideApi,
        strings.safeMode,
        strings.confirmRequired,
      ],
    ),
  ];
}

AgentChatStatus _agentStatusForPlan(AgentPlan plan) {
  if (plan.isAuthRequired) return AgentChatStatus.authRequired;
  if (plan.isBlocked) return AgentChatStatus.blocked;
  return AgentChatStatus.readyForReview;
}

String _agentPlanAssistantText(AgentPlan plan) {
  if (plan.isAuthRequired) {
    return 'Plan requires auth. No action was executed.';
  }
  if (plan.isBlocked) {
    return 'Plan is blocked by backend policy. No action was executed.';
  }
  if (plan.canPrepareManualTicket) {
    return 'Manual ticket prefill plan created. No order submitted.';
  }
  if (plan.canRunSafeAction) {
    return 'Safe action plan created for review. No order submitted.';
  }
  return 'Plan created for review. No order submitted.';
}

List<String> _agentSafetyBadges(
  AgentCommandParseResult parsed,
  AgentPlan? plan,
) {
  final badges = <String>[
    parsed.fallbackUsed ? 'FALLBACK PARSER' : 'GPT-BACKED',
    'SERVER-SIDE API',
    'NO AUTO SUBMIT',
  ];
  if (plan == null) return badges;
  if (plan.canPrepareManualTicket) {
    badges.addAll([
      'PREFILL ONLY',
      'MANUAL VALIDATION REQUIRED',
      'CONFIRM_LIVE MANUAL',
    ]);
  } else if (plan.canRunSafeAction) {
    badges.add('SAFE EXECUTION ONLY');
  }
  if (plan.isAuthRequired) badges.add('AUTH REQUIRED');
  if (plan.isBlocked) badges.add('BLOCKED');
  if (plan.riskLevel == 'read_only') badges.add('READ ONLY');
  if (plan.riskLevel == 'analysis_only') badges.add('ANALYSIS ONLY');
  return badges;
}

int? _wholeAgentPrefillQuantity(double? value) {
  if (value == null || value < 1 || value.isNaN || value.isInfinite) {
    return null;
  }
  final rounded = value.roundToDouble();
  if (rounded != value) return null;
  return rounded.toInt();
}

OpsSettings _opsSettingsWithPayload(
  OpsSettings settings,
  Map<String, dynamic> values,
) {
  final stopLoss = _payloadBool(
    values,
    'kis_limited_auto_stop_loss_enabled',
    fallbackKey: 'kis_limited_auto_sell_stop_loss_enabled',
  );
  final takeProfit = _payloadBool(
    values,
    'kis_limited_auto_take_profit_enabled',
    fallbackKey: 'kis_limited_auto_sell_take_profit_enabled',
  );
  final krNoNewEntryAfter = _payloadString(values, 'kr_no_new_entry_after') ??
      _payloadString(values, 'no_new_entry_after') ??
      _payloadString(values, 'kis_limited_auto_buy_no_new_entry_after');
  return settings.copyWith(
    schedulerEnabled:
        _payloadBool(values, 'scheduler_enabled') ?? settings.schedulerEnabled,
    dryRun: _payloadBool(values, 'dry_run') ?? settings.dryRun,
    killSwitch: _payloadBool(values, 'kill_switch') ?? settings.killSwitch,
    currentOperationMode: _payloadString(values, 'operation_mode') ??
        settings.currentOperationMode,
    maxDailyTrades:
        _payloadInt(values, 'max_trades_per_day') ?? settings.maxDailyTrades,
    maxLiveOrdersPerDay: _payloadInt(values, 'max_live_orders_per_day') ??
        _payloadInt(values, 'kis_scheduler_max_live_orders_per_day') ??
        settings.maxLiveOrdersPerDay,
    maxPositions: _payloadInt(values, 'max_positions') ??
        _payloadInt(values, 'max_open_positions') ??
        _payloadInt(values, 'kis_limited_auto_buy_max_positions') ??
        settings.maxPositions,
    maxPositionPct:
        _payloadDouble(values, 'max_position_pct') ?? settings.maxPositionPct,
    maxOrderNotionalPct: _payloadDouble(values, 'max_order_notional_pct') ??
        _payloadDouble(values, 'kis_limited_auto_sell_max_notional_pct') ??
        settings.maxOrderNotionalPct,
    dailyMaxLossPct: _payloadDouble(values, 'daily_max_loss_pct') ??
        settings.dailyMaxLossPct,
    noNewEntryAfter: krNoNewEntryAfter ?? settings.noNewEntryAfter,
    krNoNewEntryAfter: krNoNewEntryAfter ?? settings.krNoNewEntryAfter,
    stopLossPct:
        _payloadDouble(values, 'stop_loss_pct') ?? settings.stopLossPct,
    takeProfitPct:
        _payloadDouble(values, 'take_profit_pct') ?? settings.takeProfitPct,
    kisSchedulerEnabled: _payloadBool(values, 'kis_scheduler_enabled') ??
        settings.kisSchedulerEnabled,
    kisSchedulerDryRun: _payloadBool(values, 'kis_scheduler_dry_run') ??
        settings.kisSchedulerDryRun,
    kisSchedulerLiveEnabled:
        _payloadBool(values, 'kis_scheduler_live_enabled') ??
            settings.kisSchedulerLiveEnabled,
    kisSchedulerAllowRealOrders:
        _payloadBool(values, 'kis_scheduler_allow_real_orders') ??
            settings.kisSchedulerAllowRealOrders,
    kisSchedulerConfiguredAllowRealOrders:
        _payloadBool(values, 'kis_scheduler_configured_allow_real_orders') ??
            settings.kisSchedulerConfiguredAllowRealOrders,
    kisSchedulerSellEnabled:
        _payloadBool(values, 'kis_scheduler_sell_enabled') ??
            settings.kisSchedulerSellEnabled,
    kisSchedulerBuyEnabled: _payloadBool(values, 'kis_scheduler_buy_enabled') ??
        settings.kisSchedulerBuyEnabled,
    kisLiveAutoSellEnabled:
        _payloadBool(values, 'kis_live_auto_sell_enabled') ??
            settings.kisLiveAutoSellEnabled,
    kisLiveAutoBuyEnabled: _payloadBool(values, 'kis_live_auto_buy_enabled') ??
        settings.kisLiveAutoBuyEnabled,
    kisLimitedAutoSellEnabled:
        _payloadBool(values, 'kis_limited_auto_sell_enabled') ??
            settings.kisLimitedAutoSellEnabled,
    kisLimitedAutoStopLossEnabled:
        stopLoss ?? settings.kisLimitedAutoStopLossEnabled,
    kisLimitedAutoSellStopLossEnabled:
        stopLoss ?? settings.kisLimitedAutoSellStopLossEnabled,
    kisLimitedAutoTakeProfitEnabled:
        takeProfit ?? settings.kisLimitedAutoTakeProfitEnabled,
    kisLimitedAutoSellTakeProfitEnabled:
        takeProfit ?? settings.kisLimitedAutoSellTakeProfitEnabled,
    kisLimitedAutoSellAllowTakeProfitTrigger: _payloadBool(
            values, 'kis_limited_auto_sell_allow_take_profit_trigger') ??
        settings.kisLimitedAutoSellAllowTakeProfitTrigger,
    kisLimitedAutoSellMaxOrdersPerDay:
        _payloadInt(values, 'kis_limited_auto_sell_max_orders_per_day') ??
            settings.kisLimitedAutoSellMaxOrdersPerDay,
    kisLimitedAutoSellMaxNotionalPct:
        _payloadDouble(values, 'kis_limited_auto_sell_max_notional_pct') ??
            settings.kisLimitedAutoSellMaxNotionalPct,
    kisLimitedAutoBuyEnabled:
        _payloadBool(values, 'kis_limited_auto_buy_enabled') ??
            settings.kisLimitedAutoBuyEnabled,
    kisLimitedAutoBuyRequiresShadowReview: _payloadBool(
          values,
          'kis_limited_auto_buy_requires_shadow_review',
        ) ??
        settings.kisLimitedAutoBuyRequiresShadowReview,
    kisLimitedAutoBuyNoNewEntryAfter:
        krNoNewEntryAfter ?? settings.kisLimitedAutoBuyNoNewEntryAfter,
    kisSchedulerAllowLimitedAutoSell:
        _payloadBool(values, 'kis_scheduler_allow_limited_auto_sell') ??
            settings.kisSchedulerAllowLimitedAutoSell,
    kisSchedulerAllowLimitedAutoBuy:
        _payloadBool(values, 'kis_scheduler_allow_limited_auto_buy') ??
            settings.kisSchedulerAllowLimitedAutoBuy,
    kisSchedulerMaxLiveOrdersPerDay:
        _payloadInt(values, 'kis_scheduler_max_live_orders_per_day') ??
            _payloadInt(values, 'max_live_orders_per_day') ??
            settings.kisSchedulerMaxLiveOrdersPerDay,
  );
}

bool? _payloadBool(
  Map<String, dynamic> values,
  String key, {
  String? fallbackKey,
}) {
  if (values.containsKey(key)) return _dynamicBool(values[key]);
  if (fallbackKey != null && values.containsKey(fallbackKey)) {
    return _dynamicBool(values[fallbackKey]);
  }
  return null;
}

bool? _dynamicBool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

int? _payloadInt(Map<String, dynamic> values, String key) {
  if (!values.containsKey(key)) return null;
  final value = values[key];
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

double? _payloadDouble(Map<String, dynamic> values, String key) {
  if (!values.containsKey(key)) return null;
  final value = values[key];
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}

String? _payloadString(Map<String, dynamic> values, String key) {
  if (!values.containsKey(key)) return null;
  final text = values[key]?.toString().trim();
  if (text == null || text.isEmpty) return null;
  return text;
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

String _firstNonEmpty(List<Object?> values) {
  for (final value in values) {
    final text = value?.toString().trim();
    if (text != null && text.isNotEmpty && text != 'null') return text;
  }
  return '';
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

TradingRun _tradingRunFromLog(TradingLogItem item) {
  return TradingRun(
    timestamp: item.createdAt,
    triggerSource: item.triggerSource,
    symbol: item.symbol,
    result: item.result,
    reason: item.reason,
    bestScore: 0,
    orderId: item.relatedOrderId,
    action: item.action,
    gateLevel: item.gateLevel,
  );
}

String _localTimestampNow() {
  final now = DateTime.now();
  return now.toIso8601String();
}

String _settingsChangeSummary(
  String label,
  OpsSettings settings,
  SchedulerStatus schedulerStatus,
) {
  final normalized = label.toLowerCase();
  final risk = schedulerStatus.kr.riskSummary;
  final riskParts = [
    'Live Sell Armed ${_onOff(risk.liveSellArmed)}',
    'Live Buy Armed ${_onOff(risk.liveBuyArmed)}',
    'Daily Live Order Limit ${risk.dailyLiveOrderLimit}',
    'Max Notional ${_formatPct(risk.maxNotionalPct)}',
    'Warning Level ${risk.warningLevel}',
    if (risk.blockingFlags.isNotEmpty)
      'Block Reasons ${risk.blockingFlags.join(', ')}'
    else if (!schedulerStatus.kr.enabledForScheduler &&
        schedulerStatus.kr.enabledForSchedulerBlockReasons.isNotEmpty)
      'Block Reasons ${schedulerStatus.kr.enabledForSchedulerBlockReasons.join(', ')}',
  ];
  if (normalized.contains('sell-only')) {
    final parts = [
      'Sell-Only Test Mode enabled',
      'KIS Scheduler Effective ${_onOff(schedulerStatus.kr.enabledForScheduler)}',
      'KIS Real Order Scheduler ${_onOff(schedulerStatus.kr.realOrderSchedulerEnabled)}',
      ...riskParts,
      'KIS Sell ${_onOff(settings.kisSchedulerSellEnabled)}',
      'KIS Buy ${_onOff(settings.kisSchedulerBuyEnabled)}',
      'Dry Run ${_onOff(settings.dryRun)}',
      'Kill Switch ${_onOff(settings.killSwitch)}',
    ];
    return parts.join(' | ');
  }
  if (normalized.contains('safe mode')) {
    final parts = [
      'Safe Mode enabled',
      'KIS Scheduler Effective ${_onOff(schedulerStatus.kr.enabledForScheduler)}',
      'KIS Real Order Scheduler ${_onOff(schedulerStatus.kr.realOrderSchedulerEnabled)}',
      ...riskParts,
      'KIS Sell ${_onOff(settings.kisSchedulerSellEnabled)}',
      'KIS Buy ${_onOff(settings.kisSchedulerBuyEnabled)}',
      'Dry Run ${_onOff(settings.dryRun)}',
      'Kill Switch ${_onOff(settings.killSwitch)}',
    ];
    return parts.join(' | ');
  }
  return [
    '$label settings updated',
    'Dry Run ${_onOff(settings.dryRun)}',
    'KIS Scheduler Config ${_onOff(settings.kisSchedulerEnabled)}',
    'KIS Scheduler Effective ${_onOff(schedulerStatus.kr.enabledForScheduler)}',
    'KIS Real Order Scheduler ${_onOff(schedulerStatus.kr.realOrderSchedulerEnabled)}',
    'KIS Sell ${_onOff(settings.kisSchedulerSellEnabled)}',
    'KIS Buy ${_onOff(settings.kisSchedulerBuyEnabled)}',
  ].join(' | ');
}

String _onOff(bool enabled) => enabled ? 'ON' : 'OFF';

String _formatPct(double value) => '${(value * 100).toStringAsFixed(2)}%';

String _operationModeLabel(String preset) {
  switch (preset) {
    case 'safe_mode':
      return 'Safe Mode';
    case 'dry_run_simulation':
      return 'Dry-run Simulation';
    case 'manual_live_trading':
      return 'Manual Live Trading';
    case 'kis_sell_only_automation':
      return 'KIS Sell-only Automation';
    case 'full_live_test_mode':
      return 'Full Live Test Mode';
  }
  return preset;
}

String _agentChatPresetLabel(String preset) {
  switch (preset) {
    case 'safe_off':
      return 'Safe Off';
    case 'chat_confirmed_test':
      return 'Chat Confirmed Test';
    case 'chat_confirmed_buy_only':
      return 'Buy Only Guarded';
    case 'chat_confirmed_sell_only':
      return 'Sell Only Guarded';
    case 'chat_confirmed_full_guarded':
      return 'Full Guarded';
  }
  return preset;
}

String _agentChatPresetAppliedMessage(
  String preset,
  List<String> changedKeys,
) {
  final changed = changedKeys.isEmpty
      ? 'no setting changes'
      : '${changedKeys.length} setting(s) changed';
  return '${_agentChatPresetLabel(preset)} applied: $changed. No order was submitted.';
}

String _guardedSellQuantityMode(PositionSellPreflightResult preflight) {
  final requested = preflight.requestedQuantity;
  final available = preflight.availableQuantity;
  if (requested == null || available == null) return 'full';
  return requested < available ? 'partial' : 'full';
}

String _guardedSellReason(PositionSellPreflightResult preflight) {
  if (preflight.stopLossTriggered) return 'stop_loss_review';
  if (preflight.takeProfitTriggered) return 'take_profit_review';
  return 'manual_exit';
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
    'source_context': 'exit_preflight_manual_sell',
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
    'source_context': 'shadow_exit_manual_sell',
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
