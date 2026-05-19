class KisSingleSymbolTradingResult {
  const KisSingleSymbolTradingResult({
    required this.status,
    required this.mode,
    required this.provider,
    required this.market,
    required this.result,
    required this.action,
    required this.reason,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.dryRun,
    required this.symbolMatch,
    required this.checks,
    required this.safety,
    required this.auditMetadata,
    required this.rawPayload,
    this.message,
    this.symbol,
    this.requestedSymbol,
    this.analyzedSymbol,
    this.returnedSymbol,
    this.quantity,
    this.amount,
    this.notional,
    this.currentPrice,
    this.primaryScore,
    this.finalEntryScore,
    this.buyScore,
    this.finalBuyScore,
    this.finalSellScore,
    this.quantBuyScore,
    this.quantSellScore,
    this.aiBuyScore,
    this.aiSellScore,
    this.gptBuyScore,
    this.gptSellScore,
    this.confidence,
    this.gptReason,
    this.blockReason,
    this.noOrderReason,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    this.orderStatus,
    this.rejectionReason,
    this.createdAt,
    this.indicatorStatus,
    this.indicatorBarCount,
    this.indicatorPayload = const {},
    this.effectiveMinEntryScore,
    this.estimatedOrderAmount,
    this.availableCash,
    this.validationBlockReasons = const [],
    this.validationWarnings = const [],
    this.riskFlags = const [],
    this.gatingNotes = const [],
  });

  factory KisSingleSymbolTradingResult.fromJson(Map<String, dynamic> json) {
    final payload = Map<String, dynamic>.from(json);
    final safety = _dynamicMap(json['safety_summary'] ?? json['safety']);
    final analysis = _dynamicMap(json['analysis']);
    final readiness = _dynamicMap(json['readiness']);
    final validation = _dynamicMap(json['validation']);
    final riskFlags = _stringList(json['risk_flags']);
    final gatingNotes = _stringList(json['gating_notes']);
    return KisSingleSymbolTradingResult(
      status: _stringValue(json['status'], fallback: 'ok'),
      mode:
          _stringValue(json['mode'], fallback: 'kis_single_symbol_analyze_buy'),
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      reason: _stringValue(json['reason'], fallback: ''),
      message: _nullableString(json['message']),
      symbol: _nullableString(json['symbol']),
      requestedSymbol: _nullableString(json['requested_symbol']),
      analyzedSymbol: _nullableString(json['analyzed_symbol']),
      returnedSymbol: _nullableString(json['returned_symbol']),
      symbolMatch: _boolValue(json['symbol_match']) ?? true,
      quantity: _nullableInt(json['quantity'] ?? json['qty']),
      amount: _nullableDouble(json['amount']),
      notional: _nullableDouble(json['notional']),
      currentPrice:
          _nullableDouble(json['current_price'] ?? analysis['current_price']),
      primaryScore: _nullableDouble(json['primary_score'] ??
          json['final_score'] ??
          analysis['final_buy_score'] ??
          analysis['final_entry_score'] ??
          analysis['score']),
      finalEntryScore: _nullableDouble(json['final_entry_score'] ??
          json['final_score'] ??
          analysis['final_entry_score'] ??
          analysis['score']),
      buyScore: _nullableDouble(json['buy_score'] ?? analysis['buy_score']),
      finalBuyScore: _nullableDouble(json['final_buy_score'] ??
          json['final_score'] ??
          analysis['final_buy_score'] ??
          analysis['score']),
      finalSellScore: _nullableDouble(
          json['final_sell_score'] ?? analysis['final_sell_score']),
      quantBuyScore: _nullableDouble(json['quant_buy_score'] ??
          json['quant_score'] ??
          analysis['quant_buy_score'] ??
          analysis['quant_score']),
      quantSellScore: _nullableDouble(
          json['quant_sell_score'] ?? analysis['quant_sell_score']),
      aiBuyScore:
          _nullableDouble(json['ai_buy_score'] ?? analysis['ai_buy_score']),
      aiSellScore:
          _nullableDouble(json['ai_sell_score'] ?? analysis['ai_sell_score']),
      gptBuyScore:
          _nullableDouble(json['gpt_buy_score'] ?? analysis['gpt_buy_score']),
      gptSellScore:
          _nullableDouble(json['gpt_sell_score'] ?? analysis['gpt_sell_score']),
      confidence: _nullableDouble(json['confidence'] ?? analysis['confidence']),
      gptReason: _nullableString(
        json['gpt_reason'] ??
            analysis['gpt_reason'] ??
            _dynamicMap(json['gpt_context'])['reason'],
      ),
      riskFlags: riskFlags.isNotEmpty
          ? riskFlags
          : _stringList(analysis['risk_flags']),
      gatingNotes: gatingNotes.isNotEmpty
          ? gatingNotes
          : _stringList(analysis['gating_notes']),
      blockReason:
          _nullableString(json['block_reason'] ?? analysis['block_reason']),
      noOrderReason: _nullableString(json['no_order_reason']),
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      orderStatus: _nullableString(json['order_status']),
      rejectionReason: _nullableString(json['rejection_reason']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      dryRun: _boolValue(json['dry_run'] ?? safety['dry_run']) ?? false,
      checks: _dynamicMap(json['checks']),
      safety: safety,
      auditMetadata: _dynamicMap(json['audit_metadata']),
      indicatorStatus: _nullableString(
          json['indicator_status'] ?? analysis['indicator_status']),
      indicatorBarCount: _nullableInt(
          json['indicator_bar_count'] ?? analysis['indicator_bar_count']),
      indicatorPayload: _dynamicMap(
          json['indicator_payload'] ?? analysis['indicator_payload']),
      effectiveMinEntryScore: _nullableDouble(
        json['effective_min_entry_score'] ??
            readiness['effective_min_entry_score'],
      ),
      estimatedOrderAmount: _nullableDouble(
        json['estimated_amount'] ??
            json['estimated_order_amount'] ??
            validation['estimated_amount'],
      ),
      availableCash: _nullableDouble(
        json['available_cash'] ?? validation['available_cash'],
      ),
      validationBlockReasons: _stringList(
        json['validation_block_reasons'] ?? validation['block_reasons'],
      ),
      validationWarnings:
          _stringList(json['validation_warnings'] ?? validation['warnings']),
      createdAt: _nullableString(json['created_at']),
      rawPayload: payload,
    );
  }

  final String status;
  final String mode;
  final String provider;
  final String market;
  final String result;
  final String action;
  final String reason;
  final String? message;
  final String? symbol;
  final String? requestedSymbol;
  final String? analyzedSymbol;
  final String? returnedSymbol;
  final bool symbolMatch;
  final int? quantity;
  final double? amount;
  final double? notional;
  final double? currentPrice;
  final double? primaryScore;
  final double? finalEntryScore;
  final double? buyScore;
  final double? finalBuyScore;
  final double? finalSellScore;
  final double? quantBuyScore;
  final double? quantSellScore;
  final double? aiBuyScore;
  final double? aiSellScore;
  final double? gptBuyScore;
  final double? gptSellScore;
  final double? confidence;
  final String? gptReason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final String? blockReason;
  final String? noOrderReason;
  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final String? orderStatus;
  final String? rejectionReason;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool dryRun;
  final Map<String, dynamic> checks;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> auditMetadata;
  final String? indicatorStatus;
  final int? indicatorBarCount;
  final Map<String, dynamic> indicatorPayload;
  final double? effectiveMinEntryScore;
  final double? estimatedOrderAmount;
  final double? availableCash;
  final List<String> validationBlockReasons;
  final List<String> validationWarnings;
  final String? createdAt;
  final Map<String, dynamic> rawPayload;

  bool get hasScoreDetails =>
      primaryScore != null ||
      buyScore != null ||
      finalBuyScore != null ||
      finalSellScore != null ||
      quantBuyScore != null ||
      quantSellScore != null ||
      aiBuyScore != null ||
      aiSellScore != null ||
      gptBuyScore != null ||
      gptSellScore != null ||
      confidence != null;

  bool safetyFlag(String key) => _boolValue(safety[key]) ?? false;

  double? get cashShortfall {
    final estimated = estimatedOrderAmount;
    final cash = availableCash;
    if (estimated == null || cash == null || cash >= estimated) return null;
    return estimated - cash;
  }
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
