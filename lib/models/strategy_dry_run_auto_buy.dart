class StrategyDryRunAutoBuyResult {
  const StrategyDryRunAutoBuyResult({
    required this.status,
    required this.action,
    required this.provider,
    required this.market,
    required this.activeProfile,
    required this.candidateCount,
    required this.candidates,
    required this.targetRiskApproved,
    required this.targetRiskResult,
    required this.recommendedNotionalKrw,
    required this.recommendedNotionalPct,
    required this.simulatedQuantity,
    required this.simulatedNotionalKrw,
    required this.reason,
    required this.riskFlags,
    required this.gatingNotes,
    required this.dataQuality,
    required this.safety,
    this.selectedSymbol,
    this.selectedSymbolName,
    this.buyScore,
    this.sellScore,
    this.finalScore,
    this.confidence,
    this.simulatedPrice,
    this.signalId,
    this.tradeRunId,
    this.simulatedOrderId,
    this.createdAt,
  });

  final String status;
  final String action;
  final String provider;
  final String market;
  final String activeProfile;
  final String? selectedSymbol;
  final String? selectedSymbolName;
  final int candidateCount;
  final List<Map<String, dynamic>> candidates;
  final double? buyScore;
  final double? sellScore;
  final double? finalScore;
  final double? confidence;
  final bool targetRiskApproved;
  final Map<String, dynamic> targetRiskResult;
  final double recommendedNotionalKrw;
  final double recommendedNotionalPct;
  final int simulatedQuantity;
  final double? simulatedPrice;
  final double simulatedNotionalKrw;
  final String reason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final int? signalId;
  final int? tradeRunId;
  final int? simulatedOrderId;
  final Map<String, dynamic> dataQuality;
  final Map<String, dynamic> safety;
  final DateTime? createdAt;

  bool get wouldBuy => action == 'would_buy';
  bool get blocked => action == 'blocked';

  factory StrategyDryRunAutoBuyResult.fromJson(Map<String, dynamic> json) {
    return StrategyDryRunAutoBuyResult(
      status: _string(json['status'], 'ok'),
      action: _string(json['action'], 'hold'),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      activeProfile: _string(json['active_profile'], 'safe'),
      selectedSymbol: _nullableString(json['selected_symbol']),
      selectedSymbolName: _nullableString(json['selected_symbol_name']),
      candidateCount: _int(json['candidate_count']),
      candidates: _maps(json['candidates']),
      buyScore: _nullableDouble(json['buy_score']),
      sellScore: _nullableDouble(json['sell_score']),
      finalScore: _nullableDouble(json['final_score']),
      confidence: _nullableDouble(json['confidence']),
      targetRiskApproved: json['target_risk_approved'] == true,
      targetRiskResult: _map(json['target_risk_result']),
      recommendedNotionalKrw: _double(json['recommended_notional_krw']),
      recommendedNotionalPct: _double(json['recommended_notional_pct']),
      simulatedQuantity: _int(json['simulated_quantity']),
      simulatedPrice: _nullableDouble(json['simulated_price']),
      simulatedNotionalKrw: _double(json['simulated_notional_krw']),
      reason: _string(json['reason'], ''),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      signalId: _nullableInt(json['signal_id']),
      tradeRunId: _nullableInt(json['trade_run_id']),
      simulatedOrderId: _nullableInt(json['simulated_order_id']),
      dataQuality: _map(json['data_quality']),
      safety: _map(json['safety']),
      createdAt: _dateTime(json['created_at']),
    );
  }
}

class StrategyDryRunAutoBuyRecent {
  const StrategyDryRunAutoBuyRecent({
    required this.provider,
    required this.market,
    required this.items,
    required this.safety,
  });

  final String provider;
  final String market;
  final List<StrategyDryRunAutoBuyResult> items;
  final Map<String, dynamic> safety;

  StrategyDryRunAutoBuyResult? get latest => items.isEmpty ? null : items.first;

  factory StrategyDryRunAutoBuyRecent.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    return StrategyDryRunAutoBuyRecent(
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      items: rawItems is List
          ? [
              for (final item in rawItems)
                if (item is Map)
                  StrategyDryRunAutoBuyResult.fromJson(
                    Map<String, dynamic>.from(item),
                  ),
            ]
          : const [],
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

double _double(Object? value) => _nullableDouble(value) ?? 0;

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString().replaceAll(',', '').trim());
}

int _int(Object? value) => _nullableInt(value) ?? 0;

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString().trim());
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item?.toString().trim().isNotEmpty == true) item.toString().trim(),
  ];
}

List<Map<String, dynamic>> _maps(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map) Map<String, dynamic>.from(item),
  ];
}

Map<String, dynamic> _map(Object? value) {
  return value is Map ? Map<String, dynamic>.from(value) : const {};
}

DateTime? _dateTime(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : DateTime.tryParse(text);
}
