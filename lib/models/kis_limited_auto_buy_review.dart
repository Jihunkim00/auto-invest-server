class KisLimitedAutoBuyReview {
  const KisLimitedAutoBuyReview({
    required this.provider,
    required this.market,
    required this.mode,
    required this.reviewOnly,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.summary,
    required this.recentDecisions,
    required this.topBlockReasons,
    required this.safety,
    required this.diagnostics,
    required this.rawPayload,
    this.latestBuyReady,
  });

  factory KisLimitedAutoBuyReview.fromJson(Map<String, dynamic> json) {
    final latest = _dynamicMap(json['latest_buy_ready']);
    return KisLimitedAutoBuyReview(
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(
        json['mode'],
        fallback: 'kis_limited_auto_buy_review',
      ),
      reviewOnly: _boolValue(json['review_only']) ?? true,
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      summary: KisLimitedAutoBuyReviewSummary.fromJson(
        _dynamicMap(json['summary']),
      ),
      recentDecisions: _decisionList(json['recent_decisions']),
      topBlockReasons: _blockReasonList(json['top_block_reasons']),
      latestBuyReady: latest.isEmpty
          ? null
          : KisLimitedAutoBuyReviewDecision.fromJson(latest),
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
  final KisLimitedAutoBuyReviewSummary summary;
  final List<KisLimitedAutoBuyReviewDecision> recentDecisions;
  final List<KisLimitedAutoBuyReviewBlockReason> topBlockReasons;
  final KisLimitedAutoBuyReviewDecision? latestBuyReady;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> diagnostics;
  final Map<String, dynamic> rawPayload;

  bool get noSubmitInvariantOk => summary.noSubmitInvariantOk;
}

class KisLimitedAutoBuyReviewSummary {
  const KisLimitedAutoBuyReviewSummary({
    required this.totalRuns,
    required this.buyReadyCount,
    required this.blockedCount,
    required this.noCandidateCount,
    required this.insufficientCashCount,
    required this.scoreThresholdNotMetCount,
    required this.sellPressureTooHighCount,
    required this.duplicatePositionCount,
    required this.duplicateOpenOrderCount,
    required this.dailyLimitReachedCount,
    required this.marketSessionBlockCount,
    required this.noNewEntryAfterBlockCount,
    required this.missingIndicatorsCount,
    required this.noSubmitInvariantOk,
    this.avgFinalBuyScore,
    this.avgFinalSellScore,
    this.avgRequiredBuyScore,
    this.avgConfidence,
    this.latestRunAt,
    this.latestCandidateSymbol,
    this.latestCandidateCompany,
  });

  factory KisLimitedAutoBuyReviewSummary.fromJson(Map<String, dynamic> json) {
    return KisLimitedAutoBuyReviewSummary(
      totalRuns: _intValue(json['total_runs']),
      buyReadyCount: _intValue(json['buy_ready_count']),
      blockedCount: _intValue(json['blocked_count']),
      noCandidateCount: _intValue(json['no_candidate_count']),
      insufficientCashCount: _intValue(json['insufficient_cash_count']),
      scoreThresholdNotMetCount:
          _intValue(json['score_threshold_not_met_count']),
      sellPressureTooHighCount: _intValue(json['sell_pressure_too_high_count']),
      duplicatePositionCount: _intValue(json['duplicate_position_count']),
      duplicateOpenOrderCount: _intValue(json['duplicate_open_order_count']),
      dailyLimitReachedCount: _intValue(json['daily_limit_reached_count']),
      marketSessionBlockCount: _intValue(json['market_session_block_count']),
      noNewEntryAfterBlockCount:
          _intValue(json['no_new_entry_after_block_count']),
      missingIndicatorsCount: _intValue(json['missing_indicators_count']),
      avgFinalBuyScore: _nullableDouble(json['avg_final_buy_score']),
      avgFinalSellScore: _nullableDouble(json['avg_final_sell_score']),
      avgRequiredBuyScore: _nullableDouble(json['avg_required_buy_score']),
      avgConfidence: _nullableDouble(json['avg_confidence']),
      latestRunAt: _nullableString(json['latest_run_at']),
      latestCandidateSymbol: _nullableString(json['latest_candidate_symbol']),
      latestCandidateCompany: _nullableString(json['latest_candidate_company']),
      noSubmitInvariantOk: _boolValue(json['no_submit_invariant_ok']) ?? true,
    );
  }

  final int totalRuns;
  final int buyReadyCount;
  final int blockedCount;
  final int noCandidateCount;
  final int insufficientCashCount;
  final int scoreThresholdNotMetCount;
  final int sellPressureTooHighCount;
  final int duplicatePositionCount;
  final int duplicateOpenOrderCount;
  final int dailyLimitReachedCount;
  final int marketSessionBlockCount;
  final int noNewEntryAfterBlockCount;
  final int missingIndicatorsCount;
  final double? avgFinalBuyScore;
  final double? avgFinalSellScore;
  final double? avgRequiredBuyScore;
  final double? avgConfidence;
  final String? latestRunAt;
  final String? latestCandidateSymbol;
  final String? latestCandidateCompany;
  final bool noSubmitInvariantOk;
}

class KisLimitedAutoBuyReviewDecision {
  const KisLimitedAutoBuyReviewDecision({
    required this.status,
    required this.result,
    required this.action,
    required this.reason,
    required this.blockReasons,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.runId,
    this.signalId,
    this.createdAt,
    this.triggerSource,
    this.symbol,
    this.companyName,
    this.finalBuyScore,
    this.requiredBuyScore,
    this.finalSellScore,
    this.confidence,
    this.buySellSpread,
    this.estimatedNotional,
    this.suggestedQuantity,
    this.cashAvailable,
    this.primaryBlockReason,
    this.gateLevel,
    this.duplicatePosition,
    this.duplicateOpenOrder,
    this.marketSessionAllowed,
    this.noNewEntryAfterBlocked,
  });

  factory KisLimitedAutoBuyReviewDecision.fromJson(Map<String, dynamic> json) {
    return KisLimitedAutoBuyReviewDecision(
      runId: _nullableInt(json['run_id']),
      signalId: _nullableInt(json['signal_id']),
      createdAt: _nullableString(json['created_at']),
      triggerSource: _nullableString(json['trigger_source']),
      symbol: _nullableString(json['symbol']),
      companyName: _nullableString(
        json['company_name'] ?? json['company'] ?? json['name'],
      ),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      status: _stringValue(json['status'], fallback: 'HOLD'),
      finalBuyScore: _nullableDouble(json['final_buy_score']),
      requiredBuyScore: _nullableDouble(json['required_buy_score']),
      finalSellScore: _nullableDouble(json['final_sell_score']),
      confidence: _nullableDouble(json['confidence']),
      buySellSpread: _nullableDouble(json['buy_sell_spread']),
      estimatedNotional: _nullableDouble(json['estimated_notional']),
      suggestedQuantity: _nullableInt(json['suggested_quantity']),
      cashAvailable: _nullableDouble(json['cash_available']),
      blockReasons: _stringList(json['block_reasons']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      reason: _stringValue(json['reason'], fallback: ''),
      gateLevel: _nullableInt(json['gate_level']),
      duplicatePosition: _boolValue(json['duplicate_position']),
      duplicateOpenOrder: _boolValue(json['duplicate_open_order']),
      marketSessionAllowed: _boolValue(json['market_session_allowed']),
      noNewEntryAfterBlocked: _boolValue(json['no_new_entry_after_blocked']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
    );
  }

  final int? runId;
  final int? signalId;
  final String? createdAt;
  final String? triggerSource;
  final String? symbol;
  final String? companyName;
  final String result;
  final String action;
  final String status;
  final double? finalBuyScore;
  final double? requiredBuyScore;
  final double? finalSellScore;
  final double? confidence;
  final double? buySellSpread;
  final double? estimatedNotional;
  final int? suggestedQuantity;
  final double? cashAvailable;
  final List<String> blockReasons;
  final String? primaryBlockReason;
  final String reason;
  final int? gateLevel;
  final bool? duplicatePosition;
  final bool? duplicateOpenOrder;
  final bool? marketSessionAllowed;
  final bool? noNewEntryAfterBlocked;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
}

class KisLimitedAutoBuyReviewBlockReason {
  const KisLimitedAutoBuyReviewBlockReason({
    required this.reason,
    required this.count,
    required this.label,
  });

  factory KisLimitedAutoBuyReviewBlockReason.fromJson(
      Map<String, dynamic> json) {
    return KisLimitedAutoBuyReviewBlockReason(
      reason: _stringValue(json['reason'], fallback: ''),
      count: _intValue(json['count']),
      label: _stringValue(json['label'], fallback: ''),
    );
  }

  final String reason;
  final int count;
  final String label;
}

List<KisLimitedAutoBuyReviewDecision> _decisionList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisLimitedAutoBuyReviewDecision.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisLimitedAutoBuyReviewBlockReason> _blockReasonList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisLimitedAutoBuyReviewBlockReason.fromJson(
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
