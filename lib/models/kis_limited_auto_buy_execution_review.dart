class KisLimitedAutoBuyExecutionReview {
  const KisLimitedAutoBuyExecutionReview({
    required this.provider,
    required this.market,
    required this.mode,
    required this.reviewOnly,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.summary,
    required this.submittedBuys,
    required this.blockedDecisions,
    required this.safetyViolations,
    required this.topBlockReasons,
    required this.dailyUsage,
    required this.safety,
    required this.diagnostics,
    required this.rawPayload,
  });

  factory KisLimitedAutoBuyExecutionReview.fromJson(Map<String, dynamic> json) {
    return KisLimitedAutoBuyExecutionReview(
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(
        json['mode'],
        fallback: 'kis_limited_auto_buy_execution_review',
      ),
      reviewOnly: _boolValue(json['review_only']) ?? true,
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      summary: KisLimitedAutoBuyExecutionReviewSummary.fromJson(
        _dynamicMap(json['summary']),
      ),
      submittedBuys: _submittedBuyList(json['submitted_buys']),
      blockedDecisions: _blockedDecisionList(json['blocked_decisions']),
      safetyViolations: _safetyViolationList(json['safety_violations']),
      topBlockReasons: _blockReasonList(json['top_block_reasons']),
      dailyUsage: _dailyUsageList(json['daily_usage']),
      safety: _dynamicMap(json['safety']),
      diagnostics: _dynamicMap(json['diagnostics']),
      rawPayload: _dynamicMap(json),
    );
  }

  final String provider;
  final String market;
  final String mode;
  final bool reviewOnly;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final KisLimitedAutoBuyExecutionReviewSummary summary;
  final List<KisLimitedAutoBuySubmittedAuditItem> submittedBuys;
  final List<KisLimitedAutoBuyBlockedDecisionItem> blockedDecisions;
  final List<KisLimitedAutoBuySafetyViolation> safetyViolations;
  final List<KisLimitedAutoBuyExecutionBlockReason> topBlockReasons;
  final List<KisLimitedAutoBuyDailyUsage> dailyUsage;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> diagnostics;
  final Map<String, dynamic> rawPayload;

  bool get noSubmitInvariantOk => summary.noSubmitInvariantOk;
}

class KisLimitedAutoBuyExecutionReviewSummary {
  const KisLimitedAutoBuyExecutionReviewSummary({
    required this.totalDecisions,
    required this.submittedBuyCount,
    required this.blockedCount,
    required this.readinessOnlyCount,
    required this.validationFailedCount,
    required this.duplicatePositionBlockCount,
    required this.duplicateOpenOrderBlockCount,
    required this.dailyLimitBlockCount,
    required this.cashBlockCount,
    required this.maxNotionalBlockCount,
    required this.marketSessionBlockCount,
    required this.noNewEntryAfterBlockCount,
    required this.scoreBlockCount,
    required this.sellPressureBlockCount,
    required this.buySellSpreadBlockCount,
    required this.noSubmitInvariantOk,
    required this.submittedRowsHaveAuditMetadata,
    required this.submittedRowsHaveOrderIds,
    required this.submittedRowsHaveKisOdnoCount,
    required this.maxDailyBuyCountObserved,
    this.latestSubmittedAt,
    this.latestBlockedAt,
    this.latestSymbol,
  });

  factory KisLimitedAutoBuyExecutionReviewSummary.fromJson(
      Map<String, dynamic> json) {
    return KisLimitedAutoBuyExecutionReviewSummary(
      totalDecisions: _intValue(json['total_decisions']),
      submittedBuyCount: _intValue(json['submitted_buy_count']),
      blockedCount: _intValue(json['blocked_count']),
      readinessOnlyCount: _intValue(json['readiness_only_count']),
      validationFailedCount: _intValue(json['validation_failed_count']),
      duplicatePositionBlockCount:
          _intValue(json['duplicate_position_block_count']),
      duplicateOpenOrderBlockCount:
          _intValue(json['duplicate_open_order_block_count']),
      dailyLimitBlockCount: _intValue(json['daily_limit_block_count']),
      cashBlockCount: _intValue(json['cash_block_count']),
      maxNotionalBlockCount: _intValue(json['max_notional_block_count']),
      marketSessionBlockCount: _intValue(json['market_session_block_count']),
      noNewEntryAfterBlockCount:
          _intValue(json['no_new_entry_after_block_count']),
      scoreBlockCount: _intValue(json['score_block_count']),
      sellPressureBlockCount: _intValue(json['sell_pressure_block_count']),
      buySellSpreadBlockCount: _intValue(json['buy_sell_spread_block_count']),
      noSubmitInvariantOk: _boolValue(json['no_submit_invariant_ok']) ?? true,
      submittedRowsHaveAuditMetadata:
          _boolValue(json['submitted_rows_have_audit_metadata']) ?? true,
      submittedRowsHaveOrderIds:
          _boolValue(json['submitted_rows_have_order_ids']) ?? true,
      submittedRowsHaveKisOdnoCount:
          _intValue(json['submitted_rows_have_kis_odno_count']),
      maxDailyBuyCountObserved: _intValue(json['max_daily_buy_count_observed']),
      latestSubmittedAt: _nullableString(json['latest_submitted_at']),
      latestBlockedAt: _nullableString(json['latest_blocked_at']),
      latestSymbol: _nullableString(json['latest_symbol']),
    );
  }

  final int totalDecisions;
  final int submittedBuyCount;
  final int blockedCount;
  final int readinessOnlyCount;
  final int validationFailedCount;
  final int duplicatePositionBlockCount;
  final int duplicateOpenOrderBlockCount;
  final int dailyLimitBlockCount;
  final int cashBlockCount;
  final int maxNotionalBlockCount;
  final int marketSessionBlockCount;
  final int noNewEntryAfterBlockCount;
  final int scoreBlockCount;
  final int sellPressureBlockCount;
  final int buySellSpreadBlockCount;
  final bool noSubmitInvariantOk;
  final bool submittedRowsHaveAuditMetadata;
  final bool submittedRowsHaveOrderIds;
  final int submittedRowsHaveKisOdnoCount;
  final int maxDailyBuyCountObserved;
  final String? latestSubmittedAt;
  final String? latestBlockedAt;
  final String? latestSymbol;
}

class KisLimitedAutoBuySubmittedAuditItem {
  const KisLimitedAutoBuySubmittedAuditItem({
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.validationCalled,
    required this.runtimeSafetySnapshot,
    required this.validationSummary,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    this.createdAt,
    this.symbol,
    this.companyName,
    this.quantity,
    this.estimatedNotional,
    this.currentPrice,
    this.finalBuyScore,
    this.requiredBuyScore,
    this.finalSellScore,
    this.confidence,
    this.gateLevel,
    this.availableCash,
    this.maxNotionalPct,
    this.source,
    this.sourceType,
    this.mode,
    this.triggerSource,
    this.brokerStatus,
    this.internalStatus,
  });

  factory KisLimitedAutoBuySubmittedAuditItem.fromJson(
      Map<String, dynamic> json) {
    return KisLimitedAutoBuySubmittedAuditItem(
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      createdAt: _nullableString(json['created_at']),
      symbol: _nullableString(json['symbol']),
      companyName: _nullableString(
        json['company_name'] ?? json['company'] ?? json['name'],
      ),
      quantity: _nullableInt(json['quantity']),
      estimatedNotional: _nullableDouble(json['estimated_notional']),
      currentPrice: _nullableDouble(json['current_price']),
      finalBuyScore: _nullableDouble(json['final_buy_score']),
      requiredBuyScore: _nullableDouble(json['required_buy_score']),
      finalSellScore: _nullableDouble(json['final_sell_score']),
      confidence: _nullableDouble(json['confidence']),
      gateLevel: _nullableInt(json['gate_level']),
      availableCash: _nullableDouble(json['available_cash']),
      maxNotionalPct: _nullableDouble(json['max_notional_pct']),
      runtimeSafetySnapshot: _dynamicMap(json['runtime_safety_snapshot']),
      validationSummary: _dynamicMap(json['validation_summary']),
      source: _nullableString(json['source']),
      sourceType: _nullableString(json['source_type']),
      mode: _nullableString(json['mode']),
      triggerSource: _nullableString(json['trigger_source']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      validationCalled: _boolValue(json['validation_called']) ?? false,
      brokerStatus: _nullableString(json['broker_status']),
      internalStatus: _nullableString(json['internal_status']),
    );
  }

  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final String? createdAt;
  final String? symbol;
  final String? companyName;
  final int? quantity;
  final double? estimatedNotional;
  final double? currentPrice;
  final double? finalBuyScore;
  final double? requiredBuyScore;
  final double? finalSellScore;
  final double? confidence;
  final int? gateLevel;
  final double? availableCash;
  final double? maxNotionalPct;
  final Map<String, dynamic> runtimeSafetySnapshot;
  final Map<String, dynamic> validationSummary;
  final String? source;
  final String? sourceType;
  final String? mode;
  final String? triggerSource;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool validationCalled;
  final String? brokerStatus;
  final String? internalStatus;
}

class KisLimitedAutoBuyBlockedDecisionItem {
  const KisLimitedAutoBuyBlockedDecisionItem({
    required this.result,
    required this.action,
    required this.blockReasons,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.runId,
    this.signalId,
    this.createdAt,
    this.symbol,
    this.companyName,
    this.primaryBlockReason,
    this.finalBuyScore,
    this.requiredBuyScore,
    this.finalSellScore,
    this.confidence,
    this.estimatedNotional,
    this.suggestedQuantity,
    this.cashAvailable,
    this.duplicatePosition,
    this.duplicateOpenOrder,
    this.dailyLimitRemaining,
  });

  factory KisLimitedAutoBuyBlockedDecisionItem.fromJson(
      Map<String, dynamic> json) {
    return KisLimitedAutoBuyBlockedDecisionItem(
      runId: _nullableInt(json['run_id']),
      signalId: _nullableInt(json['signal_id']),
      createdAt: _nullableString(json['created_at']),
      symbol: _nullableString(json['symbol']),
      companyName: _nullableString(
        json['company_name'] ?? json['company'] ?? json['name'],
      ),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      blockReasons: _stringList(json['block_reasons']),
      finalBuyScore: _nullableDouble(json['final_buy_score']),
      requiredBuyScore: _nullableDouble(json['required_buy_score']),
      finalSellScore: _nullableDouble(json['final_sell_score']),
      confidence: _nullableDouble(json['confidence']),
      estimatedNotional: _nullableDouble(json['estimated_notional']),
      suggestedQuantity: _nullableInt(json['suggested_quantity']),
      cashAvailable: _nullableDouble(json['cash_available']),
      duplicatePosition: _boolValue(json['duplicate_position']),
      duplicateOpenOrder: _boolValue(json['duplicate_open_order']),
      dailyLimitRemaining: _nullableInt(json['daily_limit_remaining']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
    );
  }

  final int? runId;
  final int? signalId;
  final String? createdAt;
  final String? symbol;
  final String? companyName;
  final String result;
  final String action;
  final String? primaryBlockReason;
  final List<String> blockReasons;
  final double? finalBuyScore;
  final double? requiredBuyScore;
  final double? finalSellScore;
  final double? confidence;
  final double? estimatedNotional;
  final int? suggestedQuantity;
  final double? cashAvailable;
  final bool? duplicatePosition;
  final bool? duplicateOpenOrder;
  final int? dailyLimitRemaining;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
}

class KisLimitedAutoBuySafetyViolation {
  const KisLimitedAutoBuySafetyViolation({
    required this.code,
    required this.reason,
    this.severity,
    this.symbol,
    this.orderId,
    this.runId,
    this.createdAt,
  });

  factory KisLimitedAutoBuySafetyViolation.fromJson(Map<String, dynamic> json) {
    return KisLimitedAutoBuySafetyViolation(
      code: _stringValue(json['code'], fallback: ''),
      reason: _stringValue(json['reason'], fallback: ''),
      severity: _nullableString(json['severity']),
      symbol: _nullableString(json['symbol']),
      orderId: _nullableInt(json['order_id']),
      runId: _nullableInt(json['run_id']),
      createdAt: _nullableString(json['created_at']),
    );
  }

  final String code;
  final String reason;
  final String? severity;
  final String? symbol;
  final int? orderId;
  final int? runId;
  final String? createdAt;
}

class KisLimitedAutoBuyExecutionBlockReason {
  const KisLimitedAutoBuyExecutionBlockReason({
    required this.reason,
    required this.count,
    required this.label,
  });

  factory KisLimitedAutoBuyExecutionBlockReason.fromJson(
      Map<String, dynamic> json) {
    return KisLimitedAutoBuyExecutionBlockReason(
      reason: _stringValue(json['reason'], fallback: ''),
      count: _intValue(json['count']),
      label: _stringValue(json['label'], fallback: ''),
    );
  }

  final String reason;
  final int count;
  final String label;
}

class KisLimitedAutoBuyDailyUsage {
  const KisLimitedAutoBuyDailyUsage({
    required this.date,
    required this.submittedBuyCount,
    required this.symbols,
    required this.totalEstimatedNotional,
    required this.dailyLimit,
    required this.limitExceeded,
  });

  factory KisLimitedAutoBuyDailyUsage.fromJson(Map<String, dynamic> json) {
    return KisLimitedAutoBuyDailyUsage(
      date: _stringValue(json['date'], fallback: ''),
      submittedBuyCount: _intValue(json['submitted_buy_count']),
      symbols: _stringList(json['symbols']),
      totalEstimatedNotional:
          _nullableDouble(json['total_estimated_notional']) ?? 0,
      dailyLimit: _intValue(json['daily_limit']),
      limitExceeded: _boolValue(json['limit_exceeded']) ?? false,
    );
  }

  final String date;
  final int submittedBuyCount;
  final List<String> symbols;
  final double totalEstimatedNotional;
  final int dailyLimit;
  final bool limitExceeded;
}

List<KisLimitedAutoBuySubmittedAuditItem> _submittedBuyList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisLimitedAutoBuySubmittedAuditItem.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisLimitedAutoBuyBlockedDecisionItem> _blockedDecisionList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisLimitedAutoBuyBlockedDecisionItem.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisLimitedAutoBuySafetyViolation> _safetyViolationList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisLimitedAutoBuySafetyViolation.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisLimitedAutoBuyExecutionBlockReason> _blockReasonList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisLimitedAutoBuyExecutionBlockReason.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisLimitedAutoBuyDailyUsage> _dailyUsageList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisLimitedAutoBuyDailyUsage.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

Map<String, dynamic> _dynamicMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
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

int _intValue(Object? value) => _nullableInt(value) ?? 0;

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString().replaceAll(',', '').trim());
}

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().replaceAll(',', '').trim();
  if (text.isEmpty) return null;
  return double.tryParse(text);
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

List<String> _stringList(Object? value) {
  if (value == null) return const [];
  if (value is String) {
    final text = value.trim();
    return text.isEmpty ? const [] : [text];
  }
  if (value is Iterable) {
    return value
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty && item != 'null')
        .toList();
  }
  return const [];
}
