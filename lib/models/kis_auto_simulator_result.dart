class KisAutoSimulatorResult {
  const KisAutoSimulatorResult({
    required this.provider,
    required this.market,
    required this.mode,
    required this.dryRun,
    required this.simulated,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.triggerSource,
    required this.result,
    required this.action,
    required this.reason,
    this.triggeredSymbol,
    this.signalId,
    this.orderId,
    this.quantBuyScore,
    this.quantSellScore,
    this.aiBuyScore,
    this.aiSellScore,
    this.confidence,
    this.finalEntryScore,
    this.finalScoreGap,
    this.riskFlags = const [],
    this.gatingNotes = const [],
  });

  final String provider;
  final String market;
  final String mode;
  final bool dryRun;
  final bool simulated;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String triggerSource;
  final String result;
  final String action;
  final String? triggeredSymbol;
  final int? signalId;
  final int? orderId;
  final String reason;
  final double? quantBuyScore;
  final double? quantSellScore;
  final double? aiBuyScore;
  final double? aiSellScore;
  final double? confidence;
  final double? finalEntryScore;
  final double? finalScoreGap;
  final List<String> riskFlags;
  final List<String> gatingNotes;

  factory KisAutoSimulatorResult.fromJson(Map<String, dynamic> json) {
    return KisAutoSimulatorResult(
      provider: json['provider']?.toString() ?? 'kis',
      market: json['market']?.toString() ?? 'KR',
      mode: json['mode']?.toString() ?? 'kis_dry_run_auto',
      dryRun: json['dry_run'] != false,
      simulated: json['simulated'] != false,
      realOrderSubmitted: json['real_order_submitted'] == true,
      brokerSubmitCalled: json['broker_submit_called'] == true,
      manualSubmitCalled: json['manual_submit_called'] == true,
      triggerSource: json['trigger_source']?.toString() ?? '',
      result: json['result']?.toString() ?? '',
      action: json['action']?.toString() ?? 'hold',
      triggeredSymbol: _readNullableString(json['triggered_symbol']),
      signalId: _readNullableInt(json['signal_id']),
      orderId: _readNullableInt(json['order_id']),
      reason: json['reason']?.toString() ?? '',
      quantBuyScore: _readNullableDouble(json['quant_buy_score']),
      quantSellScore: _readNullableDouble(json['quant_sell_score']),
      aiBuyScore: _readNullableDouble(json['ai_buy_score']),
      aiSellScore: _readNullableDouble(json['ai_sell_score']),
      confidence: _readNullableDouble(json['confidence']),
      finalEntryScore: _readNullableDouble(json['final_entry_score']),
      finalScoreGap: _readNullableDouble(json['final_score_gap']),
      riskFlags: _readStringList(json['risk_flags']),
      gatingNotes: _readStringList(json['gating_notes']),
    );
  }
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? null : text;
}

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim();
  if (text.isEmpty) return null;
  return int.tryParse(text);
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty) return null;
  return double.tryParse(text);
}

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return value.map((item) => item.toString()).toList();
}
