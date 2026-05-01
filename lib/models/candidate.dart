class Candidate {
  const Candidate({
    required this.symbol,
    required this.score,
    required this.note,
    required this.entryReady,
    required this.actionHint,
    required this.blockReason,
    this.name = '',
    this.market = '',
    this.currency = '',
    this.currentPrice,
    this.indicatorStatus = '',
    this.indicatorPayload = const {},
    this.quantBuyScore,
    this.quantSellScore,
    this.aiBuyScore,
    this.aiSellScore,
    this.finalBuyScore,
    this.finalSellScore,
    this.confidence,
    this.action = 'hold',
    this.tradeAllowed,
    this.approvedByRisk,
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.reason = '',
    this.gptReason = '',
    this.warnings = const [],
    this.blockReasons = const [],
  });

  final String symbol;
  final int? score;
  final String note;
  final bool entryReady;
  final String actionHint;
  final String? blockReason;
  final String name;
  final String market;
  final String currency;
  final double? currentPrice;
  final String indicatorStatus;
  final Map<String, dynamic> indicatorPayload;
  final double? quantBuyScore;
  final double? quantSellScore;
  final double? aiBuyScore;
  final double? aiSellScore;
  final double? finalBuyScore;
  final double? finalSellScore;
  final double? confidence;
  final String action;
  final bool? tradeAllowed;
  final bool? approvedByRisk;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final String reason;
  final String gptReason;
  final List<String> warnings;
  final List<String> blockReasons;

  bool get hasScoreBreakdown =>
      quantBuyScore != null ||
      quantSellScore != null ||
      aiBuyScore != null ||
      aiSellScore != null ||
      finalBuyScore != null ||
      finalSellScore != null ||
      confidence != null;

  bool get hasIndicatorValues =>
      indicatorPayload.values.any((value) => value != null);

  bool get hasRiskContext =>
      tradeAllowed != null ||
      approvedByRisk != null ||
      riskFlags.isNotEmpty ||
      gatingNotes.isNotEmpty ||
      blockReasons.isNotEmpty;

  factory Candidate.fromJson(Map<String, dynamic> json,
      {String scoreKey = 'score', String noteKey = 'note'}) {
    final rawScore = json[scoreKey];
    final score = rawScore is num
        ? rawScore.round()
        : int.tryParse(rawScore?.toString() ?? '');
    return Candidate(
      symbol: json['symbol']?.toString() ?? '',
      score: score,
      note: json['note']?.toString() ?? json[noteKey]?.toString() ?? '',
      entryReady: json['entry_ready'] == true,
      actionHint: json['action_hint']?.toString() ?? 'watch',
      blockReason: json['block_reason']?.toString(),
      name: json['name']?.toString() ?? '',
      market: json['market']?.toString() ?? '',
      currency: json['currency']?.toString() ?? '',
      currentPrice: _readNullableDouble(json['current_price']),
      indicatorStatus: json['indicator_status']?.toString() ?? '',
      indicatorPayload:
          Map<String, dynamic>.from((json['indicator_payload'] as Map?) ?? {}),
      quantBuyScore: _readNullableDouble(json['quant_buy_score']),
      quantSellScore: _readNullableDouble(json['quant_sell_score']),
      aiBuyScore: _readNullableDouble(json['ai_buy_score']),
      aiSellScore: _readNullableDouble(json['ai_sell_score']),
      finalBuyScore: _readNullableDouble(json['final_buy_score']),
      finalSellScore: _readNullableDouble(json['final_sell_score']),
      confidence: _readNullableDouble(json['confidence']),
      action: json['action']?.toString() ?? 'hold',
      tradeAllowed: _readNullableBool(json['trade_allowed']),
      approvedByRisk: _readNullableBool(json['approved_by_risk']),
      riskFlags: _readStringList(json['risk_flags']),
      gatingNotes: _readStringList(json['gating_notes']),
      reason: json['reason']?.toString() ?? '',
      gptReason: json['gpt_reason']?.toString() ?? '',
      warnings: _readStringList(json['warnings']),
      blockReasons: _readStringList(json['block_reasons']),
    );
  }
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty) return null;
  return double.tryParse(text);
}

bool? _readNullableBool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true') return true;
  if (text == 'false') return false;
  return null;
}

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return value.map((item) => item.toString()).toList();
}
