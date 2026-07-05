class DailyOpsSummary {
  const DailyOpsSummary({
    required this.date,
    required this.timezone,
    required this.provider,
    required this.market,
    this.generatedAt,
    required this.runtimeState,
    required this.tradeActivity,
    required this.pnlSummary,
    required this.orderSummary,
    required this.promotionSummary,
    required this.schedulerSummary,
    required this.reconciliation,
    required this.riskSummary,
    required this.details,
    required this.safety,
  });

  factory DailyOpsSummary.fromJson(Map<String, dynamic> json) {
    return DailyOpsSummary(
      date: _string(json['date'], ''),
      timezone: _string(json['timezone'], 'Asia/Seoul'),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      generatedAt: _dateTime(json['generated_at']),
      runtimeState: DailyOpsRuntimeState.fromJson(_map(json['runtime_state'])),
      tradeActivity:
          DailyOpsTradeActivity.fromJson(_map(json['trade_activity'])),
      pnlSummary: DailyOpsPnlSummary.fromJson(_map(json['pnl_summary'])),
      orderSummary: DailyOpsOrderSummary.fromJson(_map(json['order_summary'])),
      promotionSummary:
          DailyOpsPromotionSummary.fromJson(_map(json['promotion_summary'])),
      schedulerSummary:
          DailyOpsSchedulerSummary.fromJson(_map(json['scheduler_summary'])),
      reconciliation:
          DailyOpsReconciliation.fromJson(_map(json['reconciliation'])),
      riskSummary: DailyOpsRiskSummary.fromJson(_map(json['risk_summary'])),
      details: DailyOpsDetails.fromJson(_map(json['details'])),
      safety: _map(json['safety']),
    );
  }

  final String date;
  final String timezone;
  final String provider;
  final String market;
  final DateTime? generatedAt;
  final DailyOpsRuntimeState runtimeState;
  final DailyOpsTradeActivity tradeActivity;
  final DailyOpsPnlSummary pnlSummary;
  final DailyOpsOrderSummary orderSummary;
  final DailyOpsPromotionSummary promotionSummary;
  final DailyOpsSchedulerSummary schedulerSummary;
  final DailyOpsReconciliation reconciliation;
  final DailyOpsRiskSummary riskSummary;
  final DailyOpsDetails details;
  final Map<String, dynamic> safety;

  bool get hasIncompletePnl =>
      pnlSummary.incompleteCalculationCount > 0 ||
      pnlSummary.auditFlags.contains('pnl_calculation_incomplete');

  bool get isAttentionRequired =>
      reconciliation.status.toLowerCase() == 'attention_required';

  bool get isWarning => reconciliation.status.toLowerCase() == 'warning';
}

class DailyOpsRuntimeState {
  const DailyOpsRuntimeState({
    required this.dryRun,
    required this.killSwitch,
    required this.kisEnabled,
    required this.kisRealOrderEnabled,
    required this.schedulerEnabled,
    required this.schedulerDryRunOnly,
    required this.schedulerRealOrdersAllowed,
    required this.botEnabled,
    this.activeProfile,
  });

  factory DailyOpsRuntimeState.fromJson(Map<String, dynamic> json) {
    return DailyOpsRuntimeState(
      dryRun: _bool(json['dry_run'], fallback: true),
      killSwitch: _bool(json['kill_switch']),
      kisEnabled: _bool(json['kis_enabled']),
      kisRealOrderEnabled: _bool(json['kis_real_order_enabled']),
      schedulerEnabled: _bool(json['scheduler_enabled']),
      schedulerDryRunOnly:
          _bool(json['scheduler_dry_run_only'], fallback: true),
      schedulerRealOrdersAllowed: _bool(json['scheduler_real_orders_allowed']),
      botEnabled: _bool(json['bot_enabled'], fallback: true),
      activeProfile: _nullableString(json['active_profile']),
    );
  }

  final bool dryRun;
  final bool killSwitch;
  final bool kisEnabled;
  final bool kisRealOrderEnabled;
  final bool schedulerEnabled;
  final bool schedulerDryRunOnly;
  final bool schedulerRealOrdersAllowed;
  final bool botEnabled;
  final String? activeProfile;
}

class DailyOpsTradeActivity {
  const DailyOpsTradeActivity({
    required this.guardedBuyAttemptCount,
    required this.guardedSellAttemptCount,
    required this.submittedBuyCount,
    required this.submittedSellCount,
    required this.filledBuyCount,
    required this.filledSellCount,
    required this.blockedAttemptCount,
    required this.dryRunSimulatedCount,
    required this.manualLiveCount,
  });

  factory DailyOpsTradeActivity.fromJson(Map<String, dynamic> json) {
    return DailyOpsTradeActivity(
      guardedBuyAttemptCount: _int(json['guarded_buy_attempt_count']),
      guardedSellAttemptCount: _int(json['guarded_sell_attempt_count']),
      submittedBuyCount: _int(json['submitted_buy_count']),
      submittedSellCount: _int(json['submitted_sell_count']),
      filledBuyCount: _int(json['filled_buy_count']),
      filledSellCount: _int(json['filled_sell_count']),
      blockedAttemptCount: _int(json['blocked_attempt_count']),
      dryRunSimulatedCount: _int(json['dry_run_simulated_count']),
      manualLiveCount: _int(json['manual_live_count']),
    );
  }

  final int guardedBuyAttemptCount;
  final int guardedSellAttemptCount;
  final int submittedBuyCount;
  final int submittedSellCount;
  final int filledBuyCount;
  final int filledSellCount;
  final int blockedAttemptCount;
  final int dryRunSimulatedCount;
  final int manualLiveCount;
}

class DailyOpsPnlSummary {
  const DailyOpsPnlSummary({
    required this.currency,
    this.realizedPl,
    this.realizedPlPct,
    this.unrealizedPl,
    this.totalPositionValue,
    this.cash,
    required this.closedTradeCount,
    required this.openPositionCount,
    required this.incompleteCalculationCount,
    required this.auditFlags,
    required this.dataSource,
  });

  factory DailyOpsPnlSummary.fromJson(Map<String, dynamic> json) {
    return DailyOpsPnlSummary(
      currency: _string(json['currency'], 'KRW'),
      realizedPl: _nullableDouble(json['realized_pl']),
      realizedPlPct: _nullableDouble(json['realized_pl_pct']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      totalPositionValue: _nullableDouble(json['total_position_value']),
      cash: _nullableDouble(json['cash']),
      closedTradeCount: _int(json['closed_trade_count']),
      openPositionCount: _int(json['open_position_count']),
      incompleteCalculationCount: _int(json['incomplete_calculation_count']),
      auditFlags: _strings(json['audit_flags']),
      dataSource: _string(json['data_source'], 'local_order_logs'),
    );
  }

  final String currency;
  final double? realizedPl;
  final double? realizedPlPct;
  final double? unrealizedPl;
  final double? totalPositionValue;
  final double? cash;
  final int closedTradeCount;
  final int openPositionCount;
  final int incompleteCalculationCount;
  final List<String> auditFlags;
  final String dataSource;
}

class DailyOpsOrderSummary {
  const DailyOpsOrderSummary({
    required this.totalOrdersToday,
    required this.statusBuckets,
    required this.syncRequiredCount,
    required this.staleOrderCount,
    this.latestOrderStatusAt,
  });

  factory DailyOpsOrderSummary.fromJson(Map<String, dynamic> json) {
    return DailyOpsOrderSummary(
      totalOrdersToday: _int(json['total_orders_today']),
      statusBuckets: _intMap(json['status_buckets']),
      syncRequiredCount: _int(json['sync_required_count']),
      staleOrderCount: _int(json['stale_order_count']),
      latestOrderStatusAt: _dateTime(json['latest_order_status_at']),
    );
  }

  final int totalOrdersToday;
  final Map<String, int> statusBuckets;
  final int syncRequiredCount;
  final int staleOrderCount;
  final DateTime? latestOrderStatusAt;
}

class DailyOpsPromotionSummary {
  const DailyOpsPromotionSummary({
    required this.createdToday,
    required this.pending,
    required this.reviewed,
    required this.acknowledged,
    required this.dismissed,
    required this.converted,
    required this.expiredOrStale,
    required this.blockedConversionCount,
  });

  factory DailyOpsPromotionSummary.fromJson(Map<String, dynamic> json) {
    return DailyOpsPromotionSummary(
      createdToday: _int(json['created_today']),
      pending: _int(json['pending']),
      reviewed: _int(json['reviewed']),
      acknowledged: _int(json['acknowledged']),
      dismissed: _int(json['dismissed']),
      converted: _int(json['converted']),
      expiredOrStale: _int(json['expired_or_stale']),
      blockedConversionCount: _int(json['blocked_conversion_count']),
    );
  }

  final int createdToday;
  final int pending;
  final int reviewed;
  final int acknowledged;
  final int dismissed;
  final int converted;
  final int expiredOrStale;
  final int blockedConversionCount;
}

class DailyOpsSchedulerSummary {
  const DailyOpsSchedulerSummary({
    required this.schedulerEnabled,
    required this.dryRunOnly,
    required this.runCountToday,
    required this.wouldBuyCount,
    required this.holdCount,
    required this.skippedCount,
    required this.promotionCreatedCount,
    required this.realOrderSubmitted,
  });

  factory DailyOpsSchedulerSummary.fromJson(Map<String, dynamic> json) {
    return DailyOpsSchedulerSummary(
      schedulerEnabled: _bool(json['scheduler_enabled']),
      dryRunOnly: _bool(json['dry_run_only'], fallback: true),
      runCountToday: _int(json['run_count_today']),
      wouldBuyCount: _int(json['would_buy_count']),
      holdCount: _int(json['hold_count']),
      skippedCount: _int(json['skipped_count']),
      promotionCreatedCount: _int(json['promotion_created_count']),
      realOrderSubmitted: _bool(json['real_order_submitted']),
    );
  }

  final bool schedulerEnabled;
  final bool dryRunOnly;
  final int runCountToday;
  final int wouldBuyCount;
  final int holdCount;
  final int skippedCount;
  final int promotionCreatedCount;
  final bool realOrderSubmitted;
}

class DailyOpsReconciliation {
  const DailyOpsReconciliation({
    required this.status,
    required this.brokerReadAvailable,
    required this.openOrderMismatchCount,
    required this.localPendingWithoutBrokerStatusCount,
    required this.brokerOrderWithoutLocalLinkCount,
    required this.missingKisOdnoCount,
    required this.missingBrokerOrderIdCount,
    required this.staleSyncCount,
    required this.warnings,
    required this.nextSafeActions,
  });

  factory DailyOpsReconciliation.fromJson(Map<String, dynamic> json) {
    return DailyOpsReconciliation(
      status: _string(json['status'], 'unknown'),
      brokerReadAvailable: _bool(json['broker_read_available']),
      openOrderMismatchCount: _int(json['open_order_mismatch_count']),
      localPendingWithoutBrokerStatusCount:
          _int(json['local_pending_without_broker_status_count']),
      brokerOrderWithoutLocalLinkCount:
          _int(json['broker_order_without_local_link_count']),
      missingKisOdnoCount: _int(json['missing_kis_odno_count']),
      missingBrokerOrderIdCount: _int(json['missing_broker_order_id_count']),
      staleSyncCount: _int(json['stale_sync_count']),
      warnings: _strings(json['warnings']),
      nextSafeActions: _strings(json['next_safe_actions']),
    );
  }

  final String status;
  final bool brokerReadAvailable;
  final int openOrderMismatchCount;
  final int localPendingWithoutBrokerStatusCount;
  final int brokerOrderWithoutLocalLinkCount;
  final int missingKisOdnoCount;
  final int missingBrokerOrderIdCount;
  final int staleSyncCount;
  final List<String> warnings;
  final List<String> nextSafeActions;
}

class DailyOpsRiskSummary {
  const DailyOpsRiskSummary({
    required this.dailyTradeLimitUsed,
    this.dailyTradeLimitRemaining,
    required this.dailyLossLimitStatus,
    required this.killSwitchStatus,
    required this.duplicateOrderRiskCount,
    required this.openPositionCount,
    this.maxPositionWarning,
    required this.noNewEntryWindowStatus,
  });

  factory DailyOpsRiskSummary.fromJson(Map<String, dynamic> json) {
    return DailyOpsRiskSummary(
      dailyTradeLimitUsed: _int(json['daily_trade_limit_used']),
      dailyTradeLimitRemaining:
          _nullableInt(json['daily_trade_limit_remaining']),
      dailyLossLimitStatus: _string(json['daily_loss_limit_status'], 'unknown'),
      killSwitchStatus: _string(json['kill_switch_status'], 'unknown'),
      duplicateOrderRiskCount: _int(json['duplicate_order_risk_count']),
      openPositionCount: _int(json['open_position_count']),
      maxPositionWarning: _nullableString(json['max_position_warning']),
      noNewEntryWindowStatus:
          _string(json['no_new_entry_window_status'], 'unknown'),
    );
  }

  final int dailyTradeLimitUsed;
  final int? dailyTradeLimitRemaining;
  final String dailyLossLimitStatus;
  final String killSwitchStatus;
  final int duplicateOrderRiskCount;
  final int openPositionCount;
  final String? maxPositionWarning;
  final String noNewEntryWindowStatus;
}

class DailyOpsDetails {
  const DailyOpsDetails({
    required this.recentOrders,
    required this.recentPromotions,
    required this.recentGuardedBuyAttempts,
    required this.recentGuardedSellAttempts,
    required this.syncRequiredItems,
    required this.blockedItems,
    required this.lifecycleSummaryReferences,
  });

  factory DailyOpsDetails.fromJson(Map<String, dynamic> json) {
    return DailyOpsDetails(
      recentOrders: _maps(json['recent_orders']),
      recentPromotions: _maps(json['recent_promotions']),
      recentGuardedBuyAttempts: _maps(json['recent_guarded_buy_attempts']),
      recentGuardedSellAttempts: _maps(json['recent_guarded_sell_attempts']),
      syncRequiredItems: _maps(json['sync_required_items']),
      blockedItems: _maps(json['blocked_items']),
      lifecycleSummaryReferences: _maps(json['lifecycle_summary_references']),
    );
  }

  final List<Map<String, dynamic>> recentOrders;
  final List<Map<String, dynamic>> recentPromotions;
  final List<Map<String, dynamic>> recentGuardedBuyAttempts;
  final List<Map<String, dynamic>> recentGuardedSellAttempts;
  final List<Map<String, dynamic>> syncRequiredItems;
  final List<Map<String, dynamic>> blockedItems;
  final List<Map<String, dynamic>> lifecycleSummaryReferences;
}

String _string(Object? value, String fallback) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? fallback : text;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}

int _int(Object? value) => _nullableInt(value) ?? 0;

int? _nullableInt(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString().trim() ?? '');
}

double? _nullableDouble(Object? value) {
  if (value is num) return value.toDouble();
  final text = value?.toString().trim().replaceAll(',', '');
  if (text == null || text.isEmpty) return null;
  return double.tryParse(text);
}

bool _bool(Object? value, {bool fallback = false}) {
  if (value is bool) return value;
  final text = value?.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return fallback;
}

Map<String, dynamic> _map(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return const <String, dynamic>{};
}

Map<String, int> _intMap(Object? value) {
  final raw = _map(value);
  return {
    for (final entry in raw.entries) entry.key: _int(entry.value),
  };
}

List<Map<String, dynamic>> _maps(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map) Map<String, dynamic>.from(item),
  ];
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item != null && item.toString().trim().isNotEmpty)
        item.toString().trim(),
  ];
}

DateTime? _dateTime(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return null;
  return DateTime.tryParse(text);
}
