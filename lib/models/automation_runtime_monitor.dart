import 'kis_scheduler_guarded_buy.dart';
import 'kis_scheduler_guarded_sell.dart';
import 'kis_scheduler_simulation.dart';
import 'log_items.dart';
import 'managed_position.dart';
import 'ops_settings.dart';
import 'portfolio_summary.dart';
import 'scheduler_status.dart';

class AutomationRuntimeMonitor {
  const AutomationRuntimeMonitor({
    required this.readOnly,
    required this.global,
    required this.alpaca,
    required this.kis,
    required this.lastRuns,
    required this.lastOrders,
    required this.lastSignals,
    required this.warnings,
    required this.diagnostics,
  });

  factory AutomationRuntimeMonitor.fromSources({
    required OpsSettings settings,
    required SchedulerStatus schedulerStatus,
    required String selectedProvider,
    required String currentLocalTime,
    required String lastRefreshTime,
    KisSchedulerSimulationStatus? kisSchedulerStatus,
    KisSchedulerGuardedSellResult? guardedSell,
    KisSchedulerGuardedBuyResult? guardedBuy,
    List<TradingLogItem> runs = const [],
    List<OrderLogItem> orders = const [],
    List<SignalLogItem> signals = const [],
    List<String> warnings = const [],
  }) {
    final summaries = runs.map(LastAutomationRunSummary.fromRun).toList();
    final alpacaRun =
        summaries.where((run) => run.isAlpacaScheduler).firstOrNull;
    final alpacaOrder =
        orders.where((order) => order.providerKey == 'alpaca').firstOrNull;

    final kisSellRun = _latestKisSellRun(summaries);
    final kisBuyRun = _latestKisBuyRun(summaries);
    final kisOrder =
        orders.where((order) => order.providerKey == 'kis').firstOrNull;
    final lastKisTrigger = _lastKisTrigger(
      guardedSell: guardedSell,
      guardedBuy: guardedBuy,
      sellRun: kisSellRun,
      buyRun: kisBuyRun,
    );
    final kisBlockReason = _firstText([
      guardedSell?.primaryBlockReason,
      guardedBuy?.primaryBlockReason,
      guardedSell?.reason,
      guardedBuy?.reason,
      kisSellRun?.reason,
      kisBuyRun?.reason,
    ]);

    return AutomationRuntimeMonitor(
      readOnly: true,
      global: GlobalAutomationStatus(
        botEnabled: settings.botEnabled,
        dryRun: settings.dryRun,
        killSwitch: settings.killSwitch,
        schedulerEnabled: settings.schedulerEnabled,
        selectedProvider: selectedProvider,
        currentLocalTime: currentLocalTime,
        lastRefreshTime: lastRefreshTime,
      ),
      alpaca: ProviderAutomationStatus(
        provider: 'Alpaca',
        market: 'US',
        schedulerEnabled:
            settings.schedulerEnabled && schedulerStatus.us.enabledForScheduler,
        botEnabled: settings.botEnabled,
        dryRun: settings.dryRun,
        paperMode: true,
        lastRunAt: alpacaRun?.createdAt,
        lastResult: alpacaRun?.result,
        lastSymbol: alpacaRun?.symbol,
        lastAction: alpacaRun?.action,
        lastBlockReason: _firstText([alpacaRun?.reason, alpacaOrder?.reason]),
        orderSubmitted: alpacaRun?.orderSubmitted == true ||
            alpacaOrder?.realOrderSubmitted == true ||
            alpacaOrder?.brokerOrderId != null,
        orderId: _firstText([
          alpacaRun?.orderId,
          alpacaOrder?.brokerOrderId,
          alpacaOrder?.orderId?.toString(),
        ]),
        mode: alpacaRun?.mode ?? '',
      ),
      kis: KisAutomationStatus(
        schedulerEnabled: settings.kisSchedulerEnabled,
        schedulerDryRun: settings.kisSchedulerDryRun,
        schedulerAllowRealOrders: settings.kisSchedulerAllowRealOrders,
        schedulerBuyEnabled: settings.kisSchedulerBuyEnabled,
        schedulerSellEnabled: settings.kisSchedulerSellEnabled,
        liveAutoBuyEnabled: settings.kisLiveAutoBuyEnabled,
        liveAutoSellEnabled: settings.kisLiveAutoSellEnabled,
        stopLossEnabled: settings.kisLimitedAutoStopLossEnabled ||
            settings.kisLimitedAutoSellStopLossEnabled,
        takeProfitEnabled: settings.kisLimitedAutoTakeProfitEnabled ||
            settings.kisLimitedAutoSellTakeProfitEnabled,
        limitedAutoBuyEnabled: settings.kisLimitedAutoBuyEnabled,
        schedulerStatus: kisSchedulerStatus,
        guardedSell: guardedSell,
        guardedBuy: guardedBuy,
        lastSellRunAt: guardedSell?.createdAt ?? kisSellRun?.createdAt,
        lastBuyRunAt: guardedBuy?.createdAt ?? kisBuyRun?.createdAt,
        lastSellRunResult: guardedSell?.result ?? kisSellRun?.result,
        lastBuyRunResult: guardedBuy?.result ?? kisBuyRun?.result,
        lastTriggerDetected: lastKisTrigger,
        lastBlockReason: kisBlockReason,
        realOrderSubmitted: guardedSell?.realOrderSubmitted == true ||
            guardedBuy?.realOrderSubmitted == true ||
            kisSellRun?.orderSubmitted == true ||
            kisBuyRun?.orderSubmitted == true ||
            kisOrder?.realOrderSubmitted == true,
        brokerSubmitCalled: guardedSell?.brokerSubmitCalled == true ||
            guardedBuy?.brokerSubmitCalled == true ||
            kisSellRun?.brokerSubmitCalled == true ||
            kisBuyRun?.brokerSubmitCalled == true ||
            kisOrder?.brokerSubmitCalled == true,
        manualSubmitCalled: guardedSell?.manualSubmitCalled == true ||
            guardedBuy?.manualSubmitCalled == true ||
            kisSellRun?.manualSubmitCalled == true ||
            kisBuyRun?.manualSubmitCalled == true ||
            kisOrder?.manualSubmitCalled == true,
        kisOdno: _firstText([
          guardedSell?.kisOdno,
          guardedBuy?.kisOdno,
          kisOrder?.kisOdno,
        ]),
        orderId: _firstText([
          guardedSell?.orderId?.toString(),
          guardedBuy?.orderId?.toString(),
          kisOrder?.orderId?.toString(),
          kisOrder?.brokerOrderId,
        ]),
        todaySubmittedCount:
            _dailyLimitInt(guardedSell?.dailyLimit, guardedBuy?.dailyLimit, [
          'today_submitted_count',
          'submitted_today',
          'current_count',
          'orders_today',
        ]),
        dailyLimitMax:
            _dailyLimitInt(guardedSell?.dailyLimit, guardedBuy?.dailyLimit, [
                  'max_live_orders_per_day',
                  'max_orders_per_day',
                  'limit',
                ]) ??
                settings.kisSchedulerMaxLiveOrdersPerDay,
        dailyLimitRemaining:
            _dailyLimitInt(guardedSell?.dailyLimit, guardedBuy?.dailyLimit, [
          'remaining',
          'remaining_today',
          'daily_limit_remaining',
        ]),
      ),
      lastRuns: summaries,
      lastOrders: orders,
      lastSignals: signals,
      warnings: warnings,
      diagnostics: {
        'read_only': true,
        'aggregation_source': 'flutter_existing_endpoints',
        'runs_count': runs.length,
        'orders_count': orders.length,
        'signals_count': signals.length,
        'warnings_count': warnings.length,
      },
    );
  }

  final bool readOnly;
  final GlobalAutomationStatus global;
  final ProviderAutomationStatus alpaca;
  final KisAutomationStatus kis;
  final List<LastAutomationRunSummary> lastRuns;
  final List<OrderLogItem> lastOrders;
  final List<SignalLogItem> lastSignals;
  final List<String> warnings;
  final Map<String, dynamic> diagnostics;

  bool get hasWarnings => warnings.isNotEmpty;
}

class GlobalAutomationStatus {
  const GlobalAutomationStatus({
    required this.botEnabled,
    required this.dryRun,
    required this.killSwitch,
    required this.schedulerEnabled,
    required this.selectedProvider,
    required this.currentLocalTime,
    required this.lastRefreshTime,
  });

  final bool botEnabled;
  final bool dryRun;
  final bool killSwitch;
  final bool schedulerEnabled;
  final String selectedProvider;
  final String currentLocalTime;
  final String lastRefreshTime;

  String get label {
    final dryRunText = dryRun ? 'DRY RUN ON' : 'DRY RUN OFF';
    final killSwitchText = killSwitch ? 'Kill Switch ON' : 'Kill Switch OFF';
    return '$dryRunText | $killSwitchText';
  }
}

class ProviderAutomationStatus {
  const ProviderAutomationStatus({
    required this.provider,
    required this.market,
    required this.schedulerEnabled,
    required this.botEnabled,
    required this.dryRun,
    required this.paperMode,
    required this.lastRunAt,
    required this.lastResult,
    required this.lastSymbol,
    required this.lastAction,
    required this.lastBlockReason,
    required this.orderSubmitted,
    required this.orderId,
    required this.mode,
  });

  final String provider;
  final String market;
  final bool schedulerEnabled;
  final bool botEnabled;
  final bool dryRun;
  final bool paperMode;
  final String? lastRunAt;
  final String? lastResult;
  final String? lastSymbol;
  final String? lastAction;
  final String? lastBlockReason;
  final bool orderSubmitted;
  final String? orderId;
  final String mode;

  bool get hasRecentRun => lastRunAt != null && lastRunAt!.trim().isNotEmpty;

  String get statusLabel {
    if (!schedulerEnabled || !botEnabled) return 'OFF';
    if (!hasRecentRun) return 'NO RECENT RUN';
    if (orderSubmitted) return 'ORDER SUBMITTED';
    final reason = lastBlockReason?.toLowerCase() ?? '';
    if (reason.contains('market_closed') || reason.contains('market closed')) {
      return 'MARKET CLOSED';
    }
    final result = lastResult?.toLowerCase() ?? '';
    if (result.contains('block') || result.contains('skip')) return 'BLOCKED';
    if (dryRun) return 'DRY RUN';
    return 'ACTIVE';
  }
}

class KisAutomationStatus {
  const KisAutomationStatus({
    required this.schedulerEnabled,
    required this.schedulerDryRun,
    required this.schedulerAllowRealOrders,
    required this.schedulerBuyEnabled,
    required this.schedulerSellEnabled,
    required this.liveAutoBuyEnabled,
    required this.liveAutoSellEnabled,
    required this.stopLossEnabled,
    required this.takeProfitEnabled,
    required this.limitedAutoBuyEnabled,
    required this.schedulerStatus,
    required this.guardedSell,
    required this.guardedBuy,
    required this.lastSellRunAt,
    required this.lastBuyRunAt,
    required this.lastSellRunResult,
    required this.lastBuyRunResult,
    required this.lastTriggerDetected,
    required this.lastBlockReason,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.kisOdno,
    required this.orderId,
    required this.todaySubmittedCount,
    required this.dailyLimitMax,
    required this.dailyLimitRemaining,
  });

  final bool schedulerEnabled;
  final bool schedulerDryRun;
  final bool schedulerAllowRealOrders;
  final bool schedulerBuyEnabled;
  final bool schedulerSellEnabled;
  final bool liveAutoBuyEnabled;
  final bool liveAutoSellEnabled;
  final bool stopLossEnabled;
  final bool takeProfitEnabled;
  final bool limitedAutoBuyEnabled;
  final KisSchedulerSimulationStatus? schedulerStatus;
  final KisSchedulerGuardedSellResult? guardedSell;
  final KisSchedulerGuardedBuyResult? guardedBuy;
  final String? lastSellRunAt;
  final String? lastBuyRunAt;
  final String? lastSellRunResult;
  final String? lastBuyRunResult;
  final String lastTriggerDetected;
  final String? lastBlockReason;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String? kisOdno;
  final String? orderId;
  final int? todaySubmittedCount;
  final int? dailyLimitMax;
  final int? dailyLimitRemaining;

  String get sellStatusLabel => _kisLegStatus(
        schedulerEnabled: schedulerEnabled,
        legEnabled: schedulerSellEnabled,
        schedulerDryRun: schedulerDryRun,
        result: guardedSell?.result ?? lastSellRunResult,
        reason: guardedSell?.primaryBlockReason ?? guardedSell?.reason,
        orderSubmitted: guardedSell?.realOrderSubmitted == true,
        hasRun: lastSellRunAt != null,
        triggerDetected:
            guardedSell?.trigger != null || lastTriggerDetected != 'none',
      );

  String get buyStatusLabel => _kisLegStatus(
        schedulerEnabled: schedulerEnabled,
        legEnabled: schedulerBuyEnabled,
        schedulerDryRun: schedulerDryRun,
        result: guardedBuy?.result ?? lastBuyRunResult,
        reason: guardedBuy?.primaryBlockReason ?? guardedBuy?.reason,
        orderSubmitted: guardedBuy?.realOrderSubmitted == true,
        hasRun: lastBuyRunAt != null,
        triggerDetected: lastTriggerDetected == 'buy_candidate',
      );
}

class LastAutomationRunSummary {
  const LastAutomationRunSummary({
    required this.provider,
    required this.market,
    required this.mode,
    required this.triggerSource,
    required this.symbol,
    required this.action,
    required this.result,
    required this.reason,
    required this.orderId,
    required this.createdAt,
    required this.orderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.exitTrigger,
    required this.source,
  });

  factory LastAutomationRunSummary.fromRun(TradingLogItem run) {
    return LastAutomationRunSummary(
      provider: run.provider,
      market: run.market,
      mode: run.mode,
      triggerSource: run.triggerSource,
      symbol: run.symbol,
      action: run.action,
      result: run.result,
      reason: run.reason,
      orderId: run.relatedOrderId,
      createdAt: run.createdAt,
      orderSubmitted:
          run.realOrderSubmitted == true || run.relatedOrderId != null,
      brokerSubmitCalled: run.brokerSubmitCalled == true,
      manualSubmitCalled: run.manualSubmitCalled == true,
      exitTrigger: run.exitTrigger,
      source: run.source,
    );
  }

  final String provider;
  final String market;
  final String mode;
  final String triggerSource;
  final String symbol;
  final String action;
  final String result;
  final String reason;
  final String? orderId;
  final String createdAt;
  final bool orderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String? exitTrigger;
  final String source;

  bool get isKis =>
      provider.trim().toLowerCase() == 'kis' ||
      market.trim().toUpperCase() == 'KR' ||
      '$mode $triggerSource $source'.toLowerCase().contains('kis');

  bool get isAlpaca => !isKis;

  bool get isAlpacaScheduler {
    if (!isAlpaca) return false;
    final hint = '$mode $triggerSource'.toLowerCase();
    return hint.contains('scheduler') ||
        hint.contains('watchlist') ||
        hint.contains('trading_run') ||
        hint.contains('run_watchlist_once') ||
        triggerSource.toLowerCase() == 'scheduler';
  }

  bool get isKisSellRun {
    if (!isKis) return false;
    final hint = '$mode $triggerSource $source $action'.toLowerCase();
    return hint.contains('guarded_sell') ||
        hint.contains('limited_auto_sell') ||
        hint.contains('exit') ||
        action.toLowerCase() == 'sell';
  }

  bool get isKisBuyRun {
    if (!isKis) return false;
    final hint = '$mode $triggerSource $source $action'.toLowerCase();
    return hint.contains('guarded_buy') ||
        hint.contains('limited_auto_buy') ||
        hint.contains('buy_shadow') ||
        action.toLowerCase() == 'buy';
  }
}

class PortfolioPositionManagementItem {
  const PortfolioPositionManagementItem({
    required this.provider,
    required this.market,
    required this.symbol,
    required this.companyName,
    required this.quantity,
    required this.averagePrice,
    required this.costBasis,
    required this.currentPrice,
    required this.currentValue,
    required this.unrealizedPl,
    required this.unrealizedPlPct,
    required this.triggerStatus,
    required this.triggerSource,
    required this.stopLossThreshold,
    required this.takeProfitThreshold,
    required this.duplicateOpenSellOrder,
    required this.latestRelatedOrder,
    required this.schedulerEligible,
    required this.manualSellAvailable,
    required this.position,
    required this.managedPosition,
  });

  factory PortfolioPositionManagementItem.fromPosition({
    required PositionSummary position,
    ManagedPosition? managedPosition,
    required bool isKr,
  }) {
    final managed = managedPosition;
    final triggerStatus = _triggerStatusFor(managed, isKr: isKr);
    final duplicateOpenSellOrder = _rawBool(managed?.rawPayload, const [
      'duplicate_open_sell_order',
      'open_sell_order_exists',
      'has_open_sell_order',
      'duplicate_order_exists',
    ]);
    final schedulerEligible = _rawBool(managed?.rawPayload, const [
          'scheduler_eligible',
          'scheduler_sell_eligible',
          'eligible_for_scheduler',
          'sell_scheduler_eligible',
        ]) ??
        (managed != null &&
            triggerStatus.priority <= TriggerStatus.sellReady.priority &&
            duplicateOpenSellOrder != true &&
            managed.blockReasons.isEmpty);

    return PortfolioPositionManagementItem(
      provider: managed?.provider ?? (isKr ? 'kis' : 'alpaca'),
      market: managed?.market ?? (isKr ? 'KR' : 'US'),
      symbol: position.symbol,
      companyName: _firstText([
            managed?.companyName,
            position.name,
          ]) ??
          'Unknown company',
      quantity: managed?.quantity ?? position.qty,
      averagePrice: managed?.averagePrice ?? position.avgEntryPrice,
      costBasis: managed?.costBasis ?? position.costBasis,
      currentPrice: managed?.currentPrice ?? position.currentPrice,
      currentValue: managed?.currentValue ?? position.marketValue,
      unrealizedPl: managed?.unrealizedPl ?? position.unrealizedPl,
      unrealizedPlPct: managed?.unrealizedPlPct ?? position.unrealizedPlpc,
      triggerStatus: triggerStatus,
      triggerSource: _triggerSourceFor(managed),
      stopLossThreshold: _rawDouble(managed?.rawPayload, const [
        'stop_loss_threshold',
        'stop_loss_threshold_pct',
        'stop_loss_pct',
      ]),
      takeProfitThreshold: _rawDouble(managed?.rawPayload, const [
        'take_profit_threshold',
        'take_profit_threshold_pct',
        'take_profit_pct',
      ]),
      duplicateOpenSellOrder: duplicateOpenSellOrder,
      latestRelatedOrder: _latestRelatedOrder(managed),
      schedulerEligible: schedulerEligible,
      manualSellAvailable:
          isKr && (managed?.canPrepareManualSell ?? position.qty.floor() > 0),
      position: position,
      managedPosition: managed,
    );
  }

  final String provider;
  final String market;
  final String symbol;
  final String companyName;
  final double quantity;
  final double? averagePrice;
  final double? costBasis;
  final double? currentPrice;
  final double? currentValue;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final TriggerStatus triggerStatus;
  final String triggerSource;
  final double? stopLossThreshold;
  final double? takeProfitThreshold;
  final bool? duplicateOpenSellOrder;
  final String? latestRelatedOrder;
  final bool schedulerEligible;
  final bool manualSellAvailable;
  final PositionSummary position;
  final ManagedPosition? managedPosition;

  static int comparePriority(
    PortfolioPositionManagementItem a,
    PortfolioPositionManagementItem b,
  ) {
    final priority =
        a.triggerStatus.priority.compareTo(b.triggerStatus.priority);
    if (priority != 0) return priority;
    return a.symbol.compareTo(b.symbol);
  }
}

enum TriggerStatus {
  stopLossReady,
  takeProfitReady,
  sellReady,
  manualReview,
  hold,
  noData;

  int get priority {
    switch (this) {
      case TriggerStatus.stopLossReady:
        return 0;
      case TriggerStatus.takeProfitReady:
        return 1;
      case TriggerStatus.sellReady:
        return 2;
      case TriggerStatus.manualReview:
        return 3;
      case TriggerStatus.hold:
        return 4;
      case TriggerStatus.noData:
        return 5;
    }
  }

  String get label {
    switch (this) {
      case TriggerStatus.stopLossReady:
        return 'STOP_LOSS_READY';
      case TriggerStatus.takeProfitReady:
        return 'TAKE_PROFIT_READY';
      case TriggerStatus.sellReady:
        return 'SELL_READY';
      case TriggerStatus.manualReview:
        return 'MANUAL_REVIEW';
      case TriggerStatus.hold:
        return 'HOLD';
      case TriggerStatus.noData:
        return 'NO_DATA';
    }
  }
}

extension _OrderLogProvider on OrderLogItem {
  String get providerKey => provider.trim().toLowerCase();
}

extension _FirstOrNull<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}

LastAutomationRunSummary? _latestKisSellRun(
  List<LastAutomationRunSummary> runs,
) {
  return runs.where((run) => run.isKisSellRun).firstOrNull;
}

LastAutomationRunSummary? _latestKisBuyRun(
  List<LastAutomationRunSummary> runs,
) {
  return runs.where((run) => run.isKisBuyRun).firstOrNull;
}

String _lastKisTrigger({
  required KisSchedulerGuardedSellResult? guardedSell,
  required KisSchedulerGuardedBuyResult? guardedBuy,
  required LastAutomationRunSummary? sellRun,
  required LastAutomationRunSummary? buyRun,
}) {
  final sellTrigger = _normalizeTrigger(
    _firstText([guardedSell?.trigger, sellRun?.exitTrigger]),
  );
  if (sellTrigger == 'stop_loss' || sellTrigger == 'take_profit') {
    return sellTrigger;
  }
  if (guardedBuy?.symbol != null || buyRun?.isKisBuyRun == true) {
    return 'buy_candidate';
  }
  return 'none';
}

String _normalizeTrigger(String? value) {
  final text = value?.trim().toLowerCase() ?? '';
  if (text.contains('stop') && text.contains('loss')) return 'stop_loss';
  if (text.contains('take') && text.contains('profit')) return 'take_profit';
  if (text.contains('buy')) return 'buy_candidate';
  return text.isEmpty ? 'none' : text;
}

String? _firstText(Iterable<Object?> values) {
  for (final value in values) {
    final text = value?.toString().trim();
    if (text != null && text.isNotEmpty && text != 'null') return text;
  }
  return null;
}

int? _dailyLimitInt(
  Map<String, dynamic>? sellLimit,
  Map<String, dynamic>? buyLimit,
  List<String> keys,
) {
  for (final payload in [sellLimit, buyLimit]) {
    if (payload == null) continue;
    for (final key in keys) {
      final value = _intValue(payload[key]);
      if (value != null) return value;
    }
  }
  return null;
}

int? _intValue(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim();
  if (text.isEmpty || text == 'null') return null;
  return int.tryParse(text);
}

String _kisLegStatus({
  required bool schedulerEnabled,
  required bool legEnabled,
  required bool schedulerDryRun,
  required String? result,
  required String? reason,
  required bool orderSubmitted,
  required bool hasRun,
  required bool triggerDetected,
}) {
  if (!schedulerEnabled || !legEnabled) return 'OFF';
  if (!hasRun) return schedulerDryRun ? 'DRY RUN' : 'NO RECENT RUN';
  if (orderSubmitted) return 'ORDER SUBMITTED';
  final reasonText = reason?.toLowerCase() ?? '';
  if (reasonText.contains('market_closed') ||
      reasonText.contains('market closed')) {
    return 'MARKET CLOSED';
  }
  final resultText = result?.toLowerCase() ?? '';
  if (resultText.contains('ready')) return 'READY';
  if (triggerDetected) return 'TRIGGER DETECTED';
  if (resultText.contains('block') || resultText.contains('skip')) {
    return 'BLOCKED';
  }
  if (schedulerDryRun) return 'DRY RUN';
  return 'READY';
}

TriggerStatus _triggerStatusFor(ManagedPosition? managed,
    {required bool isKr}) {
  if (managed == null) return isKr ? TriggerStatus.noData : TriggerStatus.hold;
  if (managed.stopLossTriggered) return TriggerStatus.stopLossReady;
  if (managed.takeProfitTriggered) return TriggerStatus.takeProfitReady;
  if (managed.isSellReady) return TriggerStatus.sellReady;
  if (managed.manualReviewRequired || managed.isReviewSell) {
    return TriggerStatus.manualReview;
  }
  return TriggerStatus.hold;
}

String _triggerSourceFor(ManagedPosition? managed) {
  if (managed == null) return 'none';
  final raw = _firstText([
    managed.rawPayload['trigger_source'],
    managed.rawPayload['exit_trigger_source'],
  ]);
  if (raw != null) return raw;
  if (managed.stopLossTriggered || managed.takeProfitTriggered) {
    return 'cost_basis_pl_pct';
  }
  if (managed.weakTrendTriggered) return 'weak_trend';
  if (managed.sellPressureTriggered) return 'sell_pressure';
  return 'none';
}

bool? _rawBool(Map<String, dynamic>? payload, List<String> keys) {
  if (payload == null) return null;
  for (final key in keys) {
    final value = payload[key];
    if (value is bool) return value;
    if (value is num) return value != 0;
    final text = value?.toString().trim().toLowerCase();
    if (text == 'true' || text == '1' || text == 'yes') return true;
    if (text == 'false' || text == '0' || text == 'no') return false;
  }
  return null;
}

double? _rawDouble(Map<String, dynamic>? payload, List<String> keys) {
  if (payload == null) return null;
  for (final key in keys) {
    final value = payload[key];
    if (value is num) return value.toDouble();
    final text = value?.toString().trim().replaceAll(',', '');
    if (text != null && text.isNotEmpty && text != 'null') {
      final parsed = double.tryParse(text);
      if (parsed != null) return parsed;
    }
  }
  return null;
}

String? _latestRelatedOrder(ManagedPosition? managed) {
  final order = managed?.latestManualSellOrder;
  if (order == null) return null;
  return _firstText([
    order['kis_odno'],
    order['broker_order_id'],
    order['order_id'],
    order['id'],
  ]);
}
