class KisBuyShadowDecision {
  const KisBuyShadowDecision({
    required this.status,
    required this.mode,
    required this.decision,
    required this.action,
    required this.reason,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.autoBuyEnabled,
    required this.autoSellEnabled,
    required this.schedulerRealOrderEnabled,
    required this.checks,
    required this.safety,
    this.symbol,
    this.candidate,
    this.createdAt,
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.failedChecks = const [],
  });

  factory KisBuyShadowDecision.fromJson(Map<String, dynamic> json) {
    final safety = _dynamicMap(json['safety']);
    return KisBuyShadowDecision(
      status: _stringValue(json['status'], fallback: 'ok'),
      mode: _stringValue(json['mode'], fallback: 'shadow_buy_dry_run'),
      decision:
          _stringValue(json['decision'] ?? json['result'], fallback: 'hold'),
      action: _stringValue(json['action'], fallback: 'hold'),
      reason: _stringValue(json['reason'], fallback: ''),
      symbol: _nullableString(json['symbol']),
      candidate: _dynamicMap(json['candidate']).isEmpty
          ? null
          : KisBuyShadowCandidate.fromJson(_dynamicMap(json['candidate'])),
      checks: _dynamicMap(json['checks']),
      safety: safety,
      realOrderSubmitted: _boolValue(
              json['real_order_submitted'] ?? safety['real_order_submitted']) ??
          false,
      brokerSubmitCalled: _boolValue(
              json['broker_submit_called'] ?? safety['broker_submit_called']) ??
          false,
      manualSubmitCalled: _boolValue(
              json['manual_submit_called'] ?? safety['manual_submit_called']) ??
          false,
      autoBuyEnabled:
          _boolValue(json['auto_buy_enabled'] ?? safety['auto_buy_enabled']) ??
              false,
      autoSellEnabled: _boolValue(
              json['auto_sell_enabled'] ?? safety['auto_sell_enabled']) ??
          false,
      schedulerRealOrderEnabled: _boolValue(
              json['scheduler_real_order_enabled'] ??
                  safety['scheduler_real_order_enabled']) ??
          false,
      createdAt: _nullableString(json['created_at']),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      failedChecks: _stringList(json['failed_checks']),
    );
  }

  final String status;
  final String mode;
  final String decision;
  final String action;
  final String reason;
  final String? symbol;
  final KisBuyShadowCandidate? candidate;
  final Map<String, dynamic> checks;
  final Map<String, dynamic> safety;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool autoBuyEnabled;
  final bool autoSellEnabled;
  final bool schedulerRealOrderEnabled;
  final String? createdAt;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<String> failedChecks;

  bool get isWouldBuy => decision.toLowerCase() == 'would_buy';
  bool get isBlocked => decision.toLowerCase() == 'blocked';

  bool check(String key) => _boolValue(checks[key]) ?? false;

  bool? nullableCheck(String key) => _boolValue(checks[key]);
}

class KisBuyShadowCandidate {
  const KisBuyShadowCandidate({
    required this.symbol,
    required this.market,
    required this.provider,
    required this.reason,
    required this.riskFlags,
    required this.gatingNotes,
    required this.auditMetadata,
    required this.gptContext,
    this.finalScore,
    this.confidence,
    this.quantScore,
    this.gptBuyScore,
    this.currentPrice,
    this.suggestedNotional,
    this.suggestedQuantity,
  });

  factory KisBuyShadowCandidate.fromJson(Map<String, dynamic> json) {
    return KisBuyShadowCandidate(
      symbol: _stringValue(json['symbol'], fallback: 'UNKNOWN'),
      market: _stringValue(json['market'], fallback: 'KR'),
      provider: _stringValue(json['provider'], fallback: 'kis'),
      finalScore: _nullableDouble(
          json['final_score'] ?? json['final_entry_score'] ?? json['score']),
      confidence: _nullableDouble(json['confidence']),
      quantScore:
          _nullableDouble(json['quant_score'] ?? json['quant_buy_score']),
      gptBuyScore:
          _nullableDouble(json['gpt_buy_score'] ?? json['ai_buy_score']),
      currentPrice: _nullableDouble(json['current_price']),
      suggestedNotional: _nullableDouble(json['suggested_notional']),
      suggestedQuantity: _nullableInt(json['suggested_quantity']),
      reason: _stringValue(json['reason'], fallback: ''),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      auditMetadata: _dynamicMap(json['audit_metadata']),
      gptContext: _dynamicMap(json['gpt_context']),
    );
  }

  final String symbol;
  final String market;
  final String provider;
  final double? finalScore;
  final double? confidence;
  final double? quantScore;
  final double? gptBuyScore;
  final double? currentPrice;
  final double? suggestedNotional;
  final int? suggestedQuantity;
  final String reason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final Map<String, dynamic> auditMetadata;
  final Map<String, dynamic> gptContext;
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

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim();
  if (text.isEmpty || text == 'null') return null;
  return int.tryParse(text);
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
