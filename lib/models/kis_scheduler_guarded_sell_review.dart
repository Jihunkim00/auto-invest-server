class KisSchedulerGuardedSellReview {
  const KisSchedulerGuardedSellReview({
    required this.provider,
    required this.market,
    required this.mode,
    required this.reviewOnly,
    required this.sellOnly,
    required this.buyExecutionAllowed,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.orderLogCreated,
    required this.summary,
    required this.recentAttempts,
    required this.submittedSells,
    required this.blockedAttempts,
    required this.topBlockReasons,
    required this.dailyUsage,
    required this.safetyViolations,
    required this.safety,
    required this.diagnostics,
    required this.rawPayload,
  });

  factory KisSchedulerGuardedSellReview.fromJson(Map<String, dynamic> json) {
    return KisSchedulerGuardedSellReview(
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(
        json['mode'],
        fallback: 'kis_scheduler_guarded_sell_review',
      ),
      reviewOnly: _boolValue(json['review_only']) ?? true,
      sellOnly: _boolValue(json['sell_only']) ?? true,
      buyExecutionAllowed: _boolValue(json['buy_execution_allowed']) ?? false,
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      orderLogCreated: _boolValue(json['order_log_created']) ?? false,
      summary: KisSchedulerGuardedSellReviewSummary.fromJson(
        _dynamicMap(json['summary']),
      ),
      recentAttempts: _attemptList(json['recent_attempts']),
      submittedSells: _submittedSellList(json['submitted_sells']),
      blockedAttempts: _blockedAttemptList(json['blocked_attempts']),
      topBlockReasons: _blockReasonList(json['top_block_reasons']),
      dailyUsage: _dailyUsageList(json['daily_usage']),
      safetyViolations: _violationList(json['safety_violations']),
      safety: _dynamicMap(json['safety']),
      diagnostics: _dynamicMap(json['diagnostics']),
      rawPayload: _dynamicMap(json),
    );
  }

  final String provider;
  final String market;
  final String mode;
  final bool reviewOnly;
  final bool sellOnly;
  final bool buyExecutionAllowed;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool orderLogCreated;
  final KisSchedulerGuardedSellReviewSummary summary;
  final List<KisSchedulerGuardedSellAttempt> recentAttempts;
  final List<KisSchedulerGuardedSellSubmittedSell> submittedSells;
  final List<KisSchedulerGuardedSellBlockedAttempt> blockedAttempts;
  final List<KisSchedulerGuardedSellBlockReason> topBlockReasons;
  final List<KisSchedulerGuardedSellDailyUsage> dailyUsage;
  final List<KisSchedulerGuardedSellSafetyViolation> safetyViolations;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> diagnostics;
  final Map<String, dynamic> rawPayload;
}

class KisSchedulerGuardedSellReviewSummary {
  const KisSchedulerGuardedSellReviewSummary({
    required this.totalAttempts,
    required this.submittedCount,
    required this.blockedCount,
    required this.failedCount,
    required this.skippedCount,
    required this.stopLossSubmitCount,
    required this.takeProfitSubmitCount,
    required this.duplicateOrderBlockCount,
    required this.dailyLimitBlockCount,
    required this.dryRunBlockCount,
    required this.killSwitchBlockCount,
    required this.schedulerDisabledBlockCount,
    required this.schedulerSellDisabledBlockCount,
    required this.schedulerRealOrdersDisabledBlockCount,
    required this.kisRealOrderDisabledBlockCount,
    required this.validationFailedCount,
    required this.noCandidateCount,
    required this.sellOnlyInvariantOk,
    required this.noDirectSchedulerSubmitInvariantOk,
    required this.buyExecutionNeverCalled,
    required this.submittedRowsHaveOrderIds,
    required this.submittedRowsHaveKisOdnoCount,
    required this.submittedRowsHaveAuditMetadata,
    required this.maxDailySellCountObserved,
    this.latestAttemptAt,
    this.latestSubmittedAt,
    this.latestBlockedAt,
    this.latestSymbol,
    this.latestResult,
  });

  factory KisSchedulerGuardedSellReviewSummary.fromJson(
    Map<String, dynamic> json,
  ) {
    return KisSchedulerGuardedSellReviewSummary(
      totalAttempts: _intValue(json['total_attempts']),
      submittedCount: _intValue(json['submitted_count']),
      blockedCount: _intValue(json['blocked_count']),
      failedCount: _intValue(json['failed_count']),
      skippedCount: _intValue(json['skipped_count']),
      stopLossSubmitCount: _intValue(json['stop_loss_submit_count']),
      takeProfitSubmitCount: _intValue(json['take_profit_submit_count']),
      duplicateOrderBlockCount: _intValue(json['duplicate_order_block_count']),
      dailyLimitBlockCount: _intValue(json['daily_limit_block_count']),
      dryRunBlockCount: _intValue(json['dry_run_block_count']),
      killSwitchBlockCount: _intValue(json['kill_switch_block_count']),
      schedulerDisabledBlockCount:
          _intValue(json['scheduler_disabled_block_count']),
      schedulerSellDisabledBlockCount:
          _intValue(json['scheduler_sell_disabled_block_count']),
      schedulerRealOrdersDisabledBlockCount:
          _intValue(json['scheduler_real_orders_disabled_block_count']),
      kisRealOrderDisabledBlockCount:
          _intValue(json['kis_real_order_disabled_block_count']),
      validationFailedCount: _intValue(json['validation_failed_count']),
      noCandidateCount: _intValue(json['no_candidate_count']),
      sellOnlyInvariantOk: _boolValue(json['sell_only_invariant_ok']) ?? true,
      noDirectSchedulerSubmitInvariantOk:
          _boolValue(json['no_direct_scheduler_submit_invariant_ok']) ?? true,
      buyExecutionNeverCalled:
          _boolValue(json['buy_execution_never_called']) ?? true,
      submittedRowsHaveOrderIds:
          _boolValue(json['submitted_rows_have_order_ids']) ?? true,
      submittedRowsHaveKisOdnoCount:
          _intValue(json['submitted_rows_have_kis_odno_count']),
      submittedRowsHaveAuditMetadata:
          _boolValue(json['submitted_rows_have_audit_metadata']) ?? true,
      maxDailySellCountObserved:
          _intValue(json['max_daily_sell_count_observed']),
      latestAttemptAt: _nullableString(json['latest_attempt_at']),
      latestSubmittedAt: _nullableString(json['latest_submitted_at']),
      latestBlockedAt: _nullableString(json['latest_blocked_at']),
      latestSymbol: _nullableString(json['latest_symbol']),
      latestResult: _nullableString(json['latest_result']),
    );
  }

  final int totalAttempts;
  final int submittedCount;
  final int blockedCount;
  final int failedCount;
  final int skippedCount;
  final int stopLossSubmitCount;
  final int takeProfitSubmitCount;
  final int duplicateOrderBlockCount;
  final int dailyLimitBlockCount;
  final int dryRunBlockCount;
  final int killSwitchBlockCount;
  final int schedulerDisabledBlockCount;
  final int schedulerSellDisabledBlockCount;
  final int schedulerRealOrdersDisabledBlockCount;
  final int kisRealOrderDisabledBlockCount;
  final int validationFailedCount;
  final int noCandidateCount;
  final bool sellOnlyInvariantOk;
  final bool noDirectSchedulerSubmitInvariantOk;
  final bool buyExecutionNeverCalled;
  final bool submittedRowsHaveOrderIds;
  final int submittedRowsHaveKisOdnoCount;
  final bool submittedRowsHaveAuditMetadata;
  final int maxDailySellCountObserved;
  final String? latestAttemptAt;
  final String? latestSubmittedAt;
  final String? latestBlockedAt;
  final String? latestSymbol;
  final String? latestResult;
}

class KisSchedulerGuardedSellAttempt {
  const KisSchedulerGuardedSellAttempt({
    required this.runId,
    required this.result,
    required this.action,
    required this.blockReasons,
    required this.sellOnly,
    required this.buyExecutionAllowed,
    required this.schedulerRealOrdersEnabled,
    required this.kisSchedulerSellEnabled,
    required this.dryRun,
    required this.killSwitch,
    required this.kisRealOrderEnabled,
    required this.kisLiveAutoSellEnabled,
    required this.stopLossEnabled,
    required this.takeProfitEnabled,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.childSellResult,
    this.createdAt,
    this.slotLabel,
    this.triggerSource,
    this.mode,
    this.symbol,
    this.companyName,
    this.primaryBlockReason,
    this.orderId,
    this.kisOdno,
    this.trigger,
  });

  factory KisSchedulerGuardedSellAttempt.fromJson(Map<String, dynamic> json) {
    return KisSchedulerGuardedSellAttempt(
      runId: _stringValue(json['run_id'], fallback: ''),
      createdAt: _nullableString(json['created_at']),
      slotLabel: _nullableString(json['slot_label']),
      triggerSource: _nullableString(json['trigger_source']),
      mode: _nullableString(json['mode']),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      symbol: _nullableString(json['symbol']),
      companyName: _nullableString(json['company_name'] ?? json['name']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      blockReasons: _stringList(json['block_reasons']),
      sellOnly: _boolValue(json['sell_only']) ?? true,
      buyExecutionAllowed: _boolValue(json['buy_execution_allowed']) ?? false,
      schedulerRealOrdersEnabled:
          _boolValue(json['scheduler_real_orders_enabled']) ?? false,
      kisSchedulerSellEnabled:
          _boolValue(json['kis_scheduler_sell_enabled']) ?? false,
      dryRun: _boolValue(json['dry_run']) ?? true,
      killSwitch: _boolValue(json['kill_switch']) ?? false,
      kisRealOrderEnabled: _boolValue(json['kis_real_order_enabled']) ?? false,
      kisLiveAutoSellEnabled:
          _boolValue(json['kis_live_auto_sell_enabled']) ?? false,
      stopLossEnabled: _boolValue(json['stop_loss_enabled']) ?? false,
      takeProfitEnabled: _boolValue(json['take_profit_enabled']) ?? false,
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      orderId: _nullableString(json['order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      trigger: _nullableString(
        json['trigger'] ?? _dynamicMap(json['child_sell_result'])['trigger'],
      ),
      childSellResult: _dynamicMap(json['child_sell_result']),
    );
  }

  final String runId;
  final String? createdAt;
  final String? slotLabel;
  final String? triggerSource;
  final String? mode;
  final String result;
  final String action;
  final String? symbol;
  final String? companyName;
  final String? primaryBlockReason;
  final List<String> blockReasons;
  final bool sellOnly;
  final bool buyExecutionAllowed;
  final bool schedulerRealOrdersEnabled;
  final bool kisSchedulerSellEnabled;
  final bool dryRun;
  final bool killSwitch;
  final bool kisRealOrderEnabled;
  final bool kisLiveAutoSellEnabled;
  final bool stopLossEnabled;
  final bool takeProfitEnabled;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String? orderId;
  final String? kisOdno;
  final String? trigger;
  final Map<String, dynamic> childSellResult;
}

class KisSchedulerGuardedSellSubmittedSell {
  const KisSchedulerGuardedSellSubmittedSell({
    required this.side,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    this.createdAt,
    this.symbol,
    this.companyName,
    this.quantity,
    this.currentPrice,
    this.estimatedNotional,
    this.trigger,
    this.source,
    this.sourceType,
    this.mode,
    this.triggerSource,
    this.parentSchedulerRunId,
    this.childLimitedAutoSellRunId,
    this.brokerStatus,
    this.internalStatus,
  });

  factory KisSchedulerGuardedSellSubmittedSell.fromJson(
    Map<String, dynamic> json,
  ) {
    return KisSchedulerGuardedSellSubmittedSell(
      orderId: _nullableString(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      createdAt: _nullableString(json['created_at']),
      symbol: _nullableString(json['symbol']),
      companyName: _nullableString(json['company_name'] ?? json['name']),
      side: _stringValue(json['side'], fallback: 'sell'),
      quantity: _nullableNum(json['quantity']),
      currentPrice: _nullableNum(json['current_price']),
      estimatedNotional: _nullableNum(json['estimated_notional']),
      trigger: _nullableString(json['trigger']),
      source: _nullableString(json['source']),
      sourceType: _nullableString(json['source_type']),
      mode: _nullableString(json['mode']),
      triggerSource: _nullableString(json['trigger_source']),
      parentSchedulerRunId: _nullableString(json['parent_scheduler_run_id']),
      childLimitedAutoSellRunId:
          _nullableString(json['child_limited_auto_sell_run_id']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      brokerStatus: _nullableString(json['broker_status']),
      internalStatus: _nullableString(json['internal_status']),
    );
  }

  final String? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final String? createdAt;
  final String? symbol;
  final String? companyName;
  final String side;
  final num? quantity;
  final num? currentPrice;
  final num? estimatedNotional;
  final String? trigger;
  final String? source;
  final String? sourceType;
  final String? mode;
  final String? triggerSource;
  final String? parentSchedulerRunId;
  final String? childLimitedAutoSellRunId;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String? brokerStatus;
  final String? internalStatus;
}

class KisSchedulerGuardedSellBlockedAttempt {
  const KisSchedulerGuardedSellBlockedAttempt({
    required this.result,
    required this.action,
    required this.blockReasons,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.runId,
    this.createdAt,
    this.symbol,
    this.primaryBlockReason,
  });

  factory KisSchedulerGuardedSellBlockedAttempt.fromJson(
    Map<String, dynamic> json,
  ) {
    return KisSchedulerGuardedSellBlockedAttempt(
      runId: _nullableString(json['run_id']),
      createdAt: _nullableString(json['created_at']),
      symbol: _nullableString(json['symbol']),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      blockReasons: _stringList(json['block_reasons']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
    );
  }

  final String? runId;
  final String? createdAt;
  final String? symbol;
  final String result;
  final String action;
  final String? primaryBlockReason;
  final List<String> blockReasons;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
}

class KisSchedulerGuardedSellBlockReason {
  const KisSchedulerGuardedSellBlockReason({
    required this.reason,
    required this.label,
    required this.count,
  });

  factory KisSchedulerGuardedSellBlockReason.fromJson(
    Map<String, dynamic> json,
  ) {
    final reason = _stringValue(json['reason'], fallback: 'unknown');
    return KisSchedulerGuardedSellBlockReason(
      reason: reason,
      label: _stringValue(json['label'], fallback: reason),
      count: _intValue(json['count']),
    );
  }

  final String reason;
  final String label;
  final int count;
}

class KisSchedulerGuardedSellDailyUsage {
  const KisSchedulerGuardedSellDailyUsage({
    required this.date,
    required this.submittedSellCount,
    required this.symbols,
    required this.triggers,
    required this.totalEstimatedNotional,
    required this.dailyLimit,
    required this.limitExceeded,
  });

  factory KisSchedulerGuardedSellDailyUsage.fromJson(
    Map<String, dynamic> json,
  ) {
    return KisSchedulerGuardedSellDailyUsage(
      date: _stringValue(json['date'], fallback: 'n/a'),
      submittedSellCount: _intValue(json['submitted_sell_count']),
      symbols: _stringList(json['symbols']),
      triggers: _stringList(json['triggers']),
      totalEstimatedNotional: _nullableNum(json['total_estimated_notional']),
      dailyLimit: _intValue(json['daily_limit']),
      limitExceeded: _boolValue(json['limit_exceeded']) ?? false,
    );
  }

  final String date;
  final int submittedSellCount;
  final List<String> symbols;
  final List<String> triggers;
  final num? totalEstimatedNotional;
  final int dailyLimit;
  final bool limitExceeded;
}

class KisSchedulerGuardedSellSafetyViolation {
  const KisSchedulerGuardedSellSafetyViolation({
    required this.reason,
    required this.label,
    this.runId,
    this.orderId,
    this.symbol,
    this.createdAt,
  });

  factory KisSchedulerGuardedSellSafetyViolation.fromJson(
    Map<String, dynamic> json,
  ) {
    final reason = _stringValue(json['reason'], fallback: 'unknown');
    return KisSchedulerGuardedSellSafetyViolation(
      reason: reason,
      label: _stringValue(json['label'], fallback: reason),
      runId: _nullableString(json['run_id']),
      orderId: _nullableString(json['order_id']),
      symbol: _nullableString(json['symbol']),
      createdAt: _nullableString(json['created_at']),
    );
  }

  final String reason;
  final String label;
  final String? runId;
  final String? orderId;
  final String? symbol;
  final String? createdAt;
}

List<KisSchedulerGuardedSellAttempt> _attemptList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisSchedulerGuardedSellAttempt.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisSchedulerGuardedSellSubmittedSell> _submittedSellList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisSchedulerGuardedSellSubmittedSell.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisSchedulerGuardedSellBlockedAttempt> _blockedAttemptList(
  Object? value,
) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisSchedulerGuardedSellBlockedAttempt.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisSchedulerGuardedSellBlockReason> _blockReasonList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisSchedulerGuardedSellBlockReason.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisSchedulerGuardedSellDailyUsage> _dailyUsageList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisSchedulerGuardedSellDailyUsage.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisSchedulerGuardedSellSafetyViolation> _violationList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisSchedulerGuardedSellSafetyViolation.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

Map<String, dynamic> _dynamicMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

String _stringValue(Object? value, {required String fallback}) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return fallback;
  return text;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

num? _nullableNum(Object? value) {
  if (value == null) return null;
  if (value is num) return value;
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return num.tryParse(text);
}

bool? _boolValue(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

int _intValue(Object? value) {
  if (value is num) return value.toInt();
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return 0;
  return int.tryParse(text) ?? 0;
}

List<String> _stringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}
