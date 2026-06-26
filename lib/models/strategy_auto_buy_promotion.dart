class StrategyAutoBuyPromotion {
  const StrategyAutoBuyPromotion({
    required this.id,
    required this.provider,
    required this.market,
    required this.status,
    required this.targetRiskResult,
    required this.riskFlags,
    required this.gatingNotes,
    required this.requestPayload,
    required this.responsePayload,
    this.activeProfile,
    this.symbol,
    this.symbolName,
    this.promotionReason,
    this.sourceDryRunSignalId,
    this.sourceDryRunTradeRunId,
    this.sourceDryRunOrderId,
    this.dryRunAction,
    this.buyScore,
    this.sellScore,
    this.finalScore,
    this.confidence,
    this.recommendedNotionalKrw,
    this.simulatedQuantity,
    this.simulatedPrice,
    this.simulatedNotionalKrw,
    this.blockReason,
    this.expiresAt,
    this.acknowledgedAt,
    this.dismissedAt,
    this.promotedToLiveAttemptId,
    this.relatedLiveOrderId,
    this.createdAt,
    this.updatedAt,
  });

  final int id;
  final String provider;
  final String market;
  final String? activeProfile;
  final String? symbol;
  final String? symbolName;
  final String status;
  final String? promotionReason;
  final int? sourceDryRunSignalId;
  final int? sourceDryRunTradeRunId;
  final int? sourceDryRunOrderId;
  final String? dryRunAction;
  final double? buyScore;
  final double? sellScore;
  final double? finalScore;
  final double? confidence;
  final double? recommendedNotionalKrw;
  final double? simulatedQuantity;
  final double? simulatedPrice;
  final double? simulatedNotionalKrw;
  final Map<String, dynamic> targetRiskResult;
  final String? blockReason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final DateTime? expiresAt;
  final DateTime? acknowledgedAt;
  final DateTime? dismissedAt;
  final int? promotedToLiveAttemptId;
  final int? relatedLiveOrderId;
  final Map<String, dynamic> requestPayload;
  final Map<String, dynamic> responsePayload;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  bool get canRunGuardedLive =>
      status == 'pending' || status == 'acknowledged';

  factory StrategyAutoBuyPromotion.fromJson(Map<String, dynamic> json) {
    return StrategyAutoBuyPromotion(
      id: _int(json['id']),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      activeProfile: _nullableString(json['active_profile']),
      symbol: _nullableString(json['symbol']),
      symbolName: _nullableString(json['symbol_name']),
      status: _string(json['status'], 'pending'),
      promotionReason: _nullableString(json['promotion_reason']),
      sourceDryRunSignalId: _nullableInt(json['source_dry_run_signal_id']),
      sourceDryRunTradeRunId:
          _nullableInt(json['source_dry_run_trade_run_id']),
      sourceDryRunOrderId: _nullableInt(json['source_dry_run_order_id']),
      dryRunAction: _nullableString(json['dry_run_action']),
      buyScore: _nullableDouble(json['buy_score']),
      sellScore: _nullableDouble(json['sell_score']),
      finalScore: _nullableDouble(json['final_score']),
      confidence: _nullableDouble(json['confidence']),
      recommendedNotionalKrw:
          _nullableDouble(json['recommended_notional_krw']),
      simulatedQuantity: _nullableDouble(json['simulated_quantity']),
      simulatedPrice: _nullableDouble(json['simulated_price']),
      simulatedNotionalKrw:
          _nullableDouble(json['simulated_notional_krw']),
      targetRiskResult: _map(json['target_risk_result']),
      blockReason: _nullableString(json['block_reason']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      expiresAt: _dateTime(json['expires_at']),
      acknowledgedAt: _dateTime(json['acknowledged_at']),
      dismissedAt: _dateTime(json['dismissed_at']),
      promotedToLiveAttemptId:
          _nullableInt(json['promoted_to_live_attempt_id']),
      relatedLiveOrderId: _nullableInt(json['related_live_order_id']),
      requestPayload: _map(json['request_payload']),
      responsePayload: _map(json['response_payload']),
      createdAt: _dateTime(json['created_at']),
      updatedAt: _dateTime(json['updated_at']),
    );
  }
}

class StrategyAutoBuyPromotions {
  const StrategyAutoBuyPromotions({
    required this.provider,
    required this.market,
    required this.count,
    required this.items,
    required this.safety,
  });

  final String provider;
  final String market;
  final int count;
  final List<StrategyAutoBuyPromotion> items;
  final Map<String, dynamic> safety;

  StrategyAutoBuyPromotion? get latest =>
      items.isEmpty ? null : items.first;

  factory StrategyAutoBuyPromotions.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    return StrategyAutoBuyPromotions(
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      count: _int(json['count']),
      items: rawItems is List
          ? [
              for (final item in rawItems)
                if (item is Map)
                  StrategyAutoBuyPromotion.fromJson(
                    Map<String, dynamic>.from(item),
                  ),
            ]
          : const [],
      safety: _map(json['safety']),
    );
  }
}

class StrategyAutoBuyPromotionActionResult {
  const StrategyAutoBuyPromotionActionResult({
    required this.status,
    required this.promotion,
    required this.safety,
  });

  final String status;
  final StrategyAutoBuyPromotion promotion;
  final Map<String, dynamic> safety;

  factory StrategyAutoBuyPromotionActionResult.fromJson(
      Map<String, dynamic> json) {
    return StrategyAutoBuyPromotionActionResult(
      status: _string(json['status'], 'unknown'),
      promotion: StrategyAutoBuyPromotion.fromJson(
        _map(json['promotion']),
      ),
      safety: _map(json['safety']),
    );
  }
}

String _string(Object? value, String fallback) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? fallback : text;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty || text == 'null' ? null : text;
}

int _int(Object? value) => _nullableInt(value) ?? 0;

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString().trim());
}

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString().replaceAll(',', '').trim());
}

DateTime? _dateTime(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return DateTime.tryParse(text);
}

Map<String, dynamic> _map(Object? value) {
  return value is Map ? Map<String, dynamic>.from(value) : const {};
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item.toString().trim().isNotEmpty) item.toString(),
  ];
}

