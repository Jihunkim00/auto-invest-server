class AutoExitCandidates {
  const AutoExitCandidates({
    required this.generatedAt,
    required this.timezone,
    required this.provider,
    required this.market,
    required this.candidates,
    required this.summary,
    required this.safetyFlags,
    required this.details,
  });

  factory AutoExitCandidates.fromJson(Map<String, dynamic> json) {
    final rawCandidates = json['candidates'];
    return AutoExitCandidates(
      generatedAt: _nullableDateTime(json['generated_at']),
      timezone: _string(json['timezone'], 'Asia/Seoul'),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      candidates: rawCandidates is List
          ? [
              for (final item in rawCandidates)
                if (item is Map)
                  AutoExitCandidate.fromJson(Map<String, dynamic>.from(item)),
            ]
          : const [],
      summary: AutoExitCandidateSummary.fromJson(_map(json['summary'])),
      safetyFlags: _strings(json['safety_flags']),
      details: _map(json['details']),
    );
  }

  final DateTime? generatedAt;
  final String timezone;
  final String provider;
  final String market;
  final List<AutoExitCandidate> candidates;
  final AutoExitCandidateSummary summary;
  final List<String> safetyFlags;
  final Map<String, dynamic> details;
}

class AutoExitCandidateSummary {
  const AutoExitCandidateSummary({
    required this.candidateCount,
    required this.criticalCount,
    required this.warningCount,
    required this.infoCount,
    required this.stopLossCount,
    required this.takeProfitCount,
    required this.trendBreakdownCount,
    required this.manualReviewCount,
    required this.duplicateSellBlockCount,
    required this.syncRequiredCount,
  });

  factory AutoExitCandidateSummary.fromJson(Map<String, dynamic> json) {
    return AutoExitCandidateSummary(
      candidateCount: _int(json['candidate_count']),
      criticalCount: _int(json['critical_count']),
      warningCount: _int(json['warning_count']),
      infoCount: _int(json['info_count']),
      stopLossCount: _int(json['stop_loss_count']),
      takeProfitCount: _int(json['take_profit_count']),
      trendBreakdownCount: _int(json['trend_breakdown_count']),
      manualReviewCount: _int(json['manual_review_count']),
      duplicateSellBlockCount: _int(json['duplicate_sell_block_count']),
      syncRequiredCount: _int(json['sync_required_count']),
    );
  }

  final int candidateCount;
  final int criticalCount;
  final int warningCount;
  final int infoCount;
  final int stopLossCount;
  final int takeProfitCount;
  final int trendBreakdownCount;
  final int manualReviewCount;
  final int duplicateSellBlockCount;
  final int syncRequiredCount;
}

class AutoExitCandidate {
  const AutoExitCandidate({
    required this.candidateId,
    required this.symbol,
    required this.provider,
    required this.market,
    required this.candidateType,
    required this.severity,
    required this.status,
    required this.actionHint,
    this.positionQuantity,
    this.availableQuantity,
    this.averagePrice,
    this.currentPrice,
    this.costBasis,
    this.currentValue,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.stopLossThresholdPct,
    this.takeProfitThresholdPct,
    required this.stopLossTriggered,
    required this.takeProfitTriggered,
    required this.trendBreakdownTriggered,
    this.momentumNote,
    required this.riskFlags,
    required this.gatingNotes,
    required this.primaryReason,
    required this.nextSafeAction,
    this.relatedPositionId,
    this.relatedBuyOrderId,
    this.relatedLifecycleId,
    required this.openSellOrderConflict,
    required this.syncRequired,
    required this.canRunSellPreflight,
    this.sellPreflightEndpointHint,
    required this.rawPayload,
  });

  factory AutoExitCandidate.fromJson(Map<String, dynamic> json) {
    return AutoExitCandidate(
      candidateId: _string(json['candidate_id'], ''),
      symbol: _string(json['symbol'], ''),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      candidateType: _string(json['candidate_type'], 'manual_review'),
      severity: _string(json['severity'], 'info'),
      status: _string(json['status'], 'unknown'),
      actionHint: _string(json['action_hint'], 'review'),
      positionQuantity: _nullableDouble(json['position_quantity']),
      availableQuantity: _nullableDouble(json['available_quantity']),
      averagePrice: _nullableDouble(json['average_price']),
      currentPrice: _nullableDouble(json['current_price']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentValue: _nullableDouble(json['current_value']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      stopLossThresholdPct: _nullableDouble(json['stop_loss_threshold_pct']),
      takeProfitThresholdPct:
          _nullableDouble(json['take_profit_threshold_pct']),
      stopLossTriggered: json['stop_loss_triggered'] == true,
      takeProfitTriggered: json['take_profit_triggered'] == true,
      trendBreakdownTriggered: json['trend_breakdown_triggered'] == true,
      momentumNote: _nullableString(json['momentum_note']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      primaryReason: _string(json['primary_reason'], ''),
      nextSafeAction: _string(json['next_safe_action'], ''),
      relatedPositionId: _nullableInt(json['related_position_id']),
      relatedBuyOrderId: _nullableInt(json['related_buy_order_id']),
      relatedLifecycleId: _nullableInt(json['related_lifecycle_id']),
      openSellOrderConflict: json['open_sell_order_conflict'] == true,
      syncRequired: json['sync_required'] == true,
      canRunSellPreflight: json['can_run_sell_preflight'] == true,
      sellPreflightEndpointHint:
          _nullableString(json['sell_preflight_endpoint_hint']),
      rawPayload: Map<String, dynamic>.from(json),
    );
  }

  final String candidateId;
  final String symbol;
  final String provider;
  final String market;
  final String candidateType;
  final String severity;
  final String status;
  final String actionHint;
  final double? positionQuantity;
  final double? availableQuantity;
  final double? averagePrice;
  final double? currentPrice;
  final double? costBasis;
  final double? currentValue;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final double? stopLossThresholdPct;
  final double? takeProfitThresholdPct;
  final bool stopLossTriggered;
  final bool takeProfitTriggered;
  final bool trendBreakdownTriggered;
  final String? momentumNote;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final String primaryReason;
  final String nextSafeAction;
  final int? relatedPositionId;
  final int? relatedBuyOrderId;
  final int? relatedLifecycleId;
  final bool openSellOrderConflict;
  final bool syncRequired;
  final bool canRunSellPreflight;
  final String? sellPreflightEndpointHint;
  final Map<String, dynamic> rawPayload;
}

String _string(dynamic value, String fallback) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? fallback : text;
}

String? _nullableString(dynamic value) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? null : text;
}

int _int(dynamic value) => _nullableInt(value) ?? 0;

int? _nullableInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

double? _nullableDouble(dynamic value) {
  if (value is num) return value.toDouble();
  return double.tryParse((value?.toString() ?? '').replaceAll(',', ''));
}

DateTime? _nullableDateTime(dynamic value) {
  final text = value?.toString().trim() ?? '';
  if (text.isEmpty) return null;
  return DateTime.tryParse(text);
}

Map<String, dynamic> _map(dynamic value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

List<String> _strings(dynamic value) {
  if (value is List) {
    return [
      for (final item in value)
        if (item != null) item.toString()
    ];
  }
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? const [] : [text];
}
