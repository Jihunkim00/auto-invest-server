class KisShadowExitReview {
  const KisShadowExitReview({
    required this.status,
    required this.mode,
    required this.reviewWindowDays,
    required this.summary,
    required this.recentDecisions,
    required this.safety,
    this.createdAt,
  });

  factory KisShadowExitReview.fromJson(Map<String, dynamic> json) {
    return KisShadowExitReview(
      status: _stringValue(json['status'], fallback: 'ok'),
      mode: _stringValue(json['mode'], fallback: 'shadow_exit_review'),
      reviewWindowDays: _intValue(json['review_window_days'], fallback: 30),
      summary: KisShadowExitReviewSummary.fromJson(json['summary']),
      recentDecisions: _decisionList(json['recent_decisions']),
      safety: KisShadowExitReviewSafety.fromJson(json['safety']),
      createdAt: _nullableString(json['created_at']),
    );
  }

  final String status;
  final String mode;
  final int reviewWindowDays;
  final KisShadowExitReviewSummary summary;
  final List<KisShadowExitReviewDecision> recentDecisions;
  final KisShadowExitReviewSafety safety;
  final String? createdAt;
}

class KisShadowExitReviewSummary {
  const KisShadowExitReviewSummary({
    required this.totalShadowRuns,
    required this.wouldSellCount,
    required this.holdCount,
    required this.manualReviewCount,
    required this.noCandidateCount,
    required this.stopLossCount,
    required this.takeProfitCount,
    required this.manualReviewTriggerCount,
    required this.insufficientCostBasisCount,
    required this.uniqueSymbolsEvaluated,
    required this.manualSellFollowedCount,
    required this.manualSellFollowedRate,
    required this.unmatchedShadowWouldSellCount,
    required this.wouldSellRate,
    required this.manualReviewRate,
    required this.noSubmitInvariantOk,
    this.latestShadowDecisionAt,
    this.latestWouldSellAt,
    this.averageUnrealizedPlPctForWouldSell,
    this.minUnrealizedPlPctForWouldSell,
    this.maxUnrealizedPlPctForWouldSell,
  });

  factory KisShadowExitReviewSummary.fromJson(Object? value) {
    final json = _mapValue(value);
    return KisShadowExitReviewSummary(
      totalShadowRuns: _intValue(json['total_shadow_runs']),
      wouldSellCount: _intValue(json['would_sell_count']),
      holdCount: _intValue(json['hold_count']),
      manualReviewCount: _intValue(json['manual_review_count']),
      noCandidateCount: _intValue(json['no_candidate_count']),
      stopLossCount: _intValue(json['stop_loss_count']),
      takeProfitCount: _intValue(json['take_profit_count']),
      manualReviewTriggerCount: _intValue(json['manual_review_trigger_count']),
      insufficientCostBasisCount:
          _intValue(json['insufficient_cost_basis_count']),
      uniqueSymbolsEvaluated: _intValue(json['unique_symbols_evaluated']),
      latestShadowDecisionAt:
          _nullableString(json['latest_shadow_decision_at']),
      latestWouldSellAt: _nullableString(json['latest_would_sell_at']),
      averageUnrealizedPlPctForWouldSell:
          _nullableDouble(json['average_unrealized_pl_pct_for_would_sell']),
      minUnrealizedPlPctForWouldSell:
          _nullableDouble(json['min_unrealized_pl_pct_for_would_sell']),
      maxUnrealizedPlPctForWouldSell:
          _nullableDouble(json['max_unrealized_pl_pct_for_would_sell']),
      wouldSellRate: _doubleValue(json['would_sell_rate']),
      manualReviewRate: _doubleValue(json['manual_review_rate']),
      manualSellFollowedCount: _intValue(json['manual_sell_followed_count']),
      manualSellFollowedRate: _doubleValue(json['manual_sell_followed_rate']),
      unmatchedShadowWouldSellCount:
          _intValue(json['unmatched_shadow_would_sell_count']),
      noSubmitInvariantOk: _boolValue(json['no_submit_invariant_ok']) ?? true,
    );
  }

  final int totalShadowRuns;
  final int wouldSellCount;
  final int holdCount;
  final int manualReviewCount;
  final int noCandidateCount;
  final int stopLossCount;
  final int takeProfitCount;
  final int manualReviewTriggerCount;
  final int insufficientCostBasisCount;
  final int uniqueSymbolsEvaluated;
  final String? latestShadowDecisionAt;
  final String? latestWouldSellAt;
  final double? averageUnrealizedPlPctForWouldSell;
  final double? minUnrealizedPlPctForWouldSell;
  final double? maxUnrealizedPlPctForWouldSell;
  final double wouldSellRate;
  final double manualReviewRate;
  final int manualSellFollowedCount;
  final double manualSellFollowedRate;
  final int unmatchedShadowWouldSellCount;
  final bool noSubmitInvariantOk;
}

class KisShadowExitReviewDecision {
  const KisShadowExitReviewDecision({
    required this.createdAt,
    required this.symbol,
    required this.decision,
    required this.action,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.runId,
    this.runKey,
    this.signalId,
    this.trigger,
    this.triggerSource,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.costBasis,
    this.currentValue,
    this.suggestedQuantity,
    this.reason = '',
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.linkedManualOrderId,
    this.linkedManualOrderStatus,
  });

  factory KisShadowExitReviewDecision.fromJson(Map<String, dynamic> json) {
    return KisShadowExitReviewDecision(
      createdAt: _stringValue(json['created_at'], fallback: ''),
      runId: _nullableInt(json['run_id']),
      runKey: _nullableString(json['run_key']),
      signalId: _nullableInt(json['signal_id']),
      symbol: _stringValue(json['symbol'], fallback: 'WATCHLIST'),
      decision: _stringValue(json['decision'], fallback: 'hold'),
      action: _stringValue(json['action'], fallback: 'hold'),
      trigger: _nullableString(json['trigger']),
      triggerSource: _nullableString(json['trigger_source']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentValue: _nullableDouble(json['current_value']),
      suggestedQuantity: _nullableDouble(json['suggested_quantity']),
      reason: _stringValue(json['reason'], fallback: ''),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      linkedManualOrderId: _nullableInt(json['linked_manual_order_id']),
      linkedManualOrderStatus:
          _nullableString(json['linked_manual_order_status']),
    );
  }

  final String createdAt;
  final int? runId;
  final String? runKey;
  final int? signalId;
  final String symbol;
  final String decision;
  final String action;
  final String? trigger;
  final String? triggerSource;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final double? costBasis;
  final double? currentValue;
  final double? suggestedQuantity;
  final String reason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final int? linkedManualOrderId;
  final String? linkedManualOrderStatus;
}

class KisShadowExitReviewSafety {
  const KisShadowExitReviewSafety({
    required this.readOnly,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.autoBuyEnabled,
    required this.autoSellEnabled,
    required this.schedulerRealOrderEnabled,
    required this.noSubmitInvariantOk,
    this.warnings = const [],
  });

  factory KisShadowExitReviewSafety.fromJson(Object? value) {
    final json = _mapValue(value);
    return KisShadowExitReviewSafety(
      readOnly: _boolValue(json['read_only']) ?? true,
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      autoBuyEnabled: _boolValue(json['auto_buy_enabled']) ?? false,
      autoSellEnabled: _boolValue(json['auto_sell_enabled']) ?? false,
      schedulerRealOrderEnabled:
          _boolValue(json['scheduler_real_order_enabled']) ?? false,
      noSubmitInvariantOk: _boolValue(json['no_submit_invariant_ok']) ?? true,
      warnings: _stringList(json['warnings']),
    );
  }

  final bool readOnly;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool autoBuyEnabled;
  final bool autoSellEnabled;
  final bool schedulerRealOrderEnabled;
  final bool noSubmitInvariantOk;
  final List<String> warnings;
}

List<KisShadowExitReviewDecision> _decisionList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) =>
          KisShadowExitReviewDecision.fromJson(Map<String, dynamic>.from(item)))
      .toList();
}

Map<String, dynamic> _mapValue(Object? value) {
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

int _intValue(Object? value, {int fallback = 0}) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString().trim() ?? '') ?? fallback;
}

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim();
  if (text.isEmpty || text == 'null') return null;
  return int.tryParse(text);
}

double _doubleValue(Object? value, {double fallback = 0}) {
  return _nullableDouble(value) ?? fallback;
}

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
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
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}
