import 'gpt_risk_context.dart';

class Candidate {
  const Candidate({
    required this.symbol,
    required this.score,
    required this.note,
    required this.entryReady,
    required this.actionHint,
    required this.blockReason,
    this.name = '',
    this.provider = '',
    this.market = '',
    this.marketLabel = '',
    this.currency = '',
    this.currentPrice,
    this.indicatorStatus = '',
    this.indicatorBarCount,
    this.indicatorPayload = const {},
    this.effectiveMinEntryScore,
    this.buySellSpread,
    this.entryScore,
    this.quantScore,
    this.quantBuyScore,
    this.quantSellScore,
    this.aiBuyScore,
    this.aiSellScore,
    this.gptBuyScore,
    this.gptSellScore,
    this.finalEntryScore,
    this.finalScore,
    this.buyScore,
    this.sellScore,
    this.finalBuyScore,
    this.finalSellScore,
    this.confidence,
    this.action = 'hold',
    this.result,
    this.status,
    this.skipReason,
    this.noOrderReason,
    this.orderId,
    this.relatedOrderId,
    this.tradeAllowed,
    this.softEntryAllowed,
    this.approvedByRisk,
    this.hardBlocked = false,
    this.hardBlockReason,
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.eventRiskLevel,
    this.entryPenalty,
    this.hardBlockNewBuy = false,
    this.allowSellOrExit = true,
    this.gptContext = GptRiskContext.empty,
    this.reason = '',
    this.gptReason = '',
    this.marketResearchReason = '',
    this.gptUsed,
    this.previewOnly,
    this.tradingEnabled,
    this.realOrderSubmitted,
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
  final String provider;
  final String market;
  final String marketLabel;
  final String currency;
  final double? currentPrice;
  final String indicatorStatus;
  final int? indicatorBarCount;
  final Map<String, dynamic> indicatorPayload;
  final double? effectiveMinEntryScore;
  final double? buySellSpread;
  final double? entryScore;
  final double? quantScore;
  final double? quantBuyScore;
  final double? quantSellScore;
  final double? aiBuyScore;
  final double? aiSellScore;
  final double? gptBuyScore;
  final double? gptSellScore;
  final double? finalEntryScore;
  final double? finalScore;
  final double? buyScore;
  final double? sellScore;
  final double? finalBuyScore;
  final double? finalSellScore;
  final double? confidence;
  final String action;
  final String? result;
  final String? status;
  final String? skipReason;
  final String? noOrderReason;
  final String? orderId;
  final String? relatedOrderId;
  final bool? tradeAllowed;
  final bool? softEntryAllowed;
  final bool? approvedByRisk;
  final bool hardBlocked;
  final String? hardBlockReason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final String? eventRiskLevel;
  final int? entryPenalty;
  final bool hardBlockNewBuy;
  final bool allowSellOrExit;
  final GptRiskContext gptContext;
  final String reason;
  final String gptReason;
  final String marketResearchReason;
  final bool? gptUsed;
  final bool? previewOnly;
  final bool? tradingEnabled;
  final bool? realOrderSubmitted;
  final List<String> warnings;
  final List<String> blockReasons;

  bool get hasScoreBreakdown =>
      entryScore != null ||
      quantScore != null ||
      quantBuyScore != null ||
      quantSellScore != null ||
      aiBuyScore != null ||
      aiSellScore != null ||
      gptBuyScore != null ||
      gptSellScore != null ||
      finalEntryScore != null ||
      finalScore != null ||
      buyScore != null ||
      sellScore != null ||
      finalBuyScore != null ||
      finalSellScore != null ||
      confidence != null;

  bool get hasIndicatorValues =>
      indicatorPayload.values.any((value) => value != null);

  bool get hasRiskContext =>
      tradeAllowed != null ||
      approvedByRisk != null ||
      hardBlocked ||
      hardBlockReason != null ||
      riskFlags.isNotEmpty ||
      gatingNotes.isNotEmpty ||
      eventRiskLevel != null ||
      entryPenalty != null ||
      hardBlockNewBuy ||
      !allowSellOrExit ||
      softEntryAllowed != null ||
      gptUsed != null ||
      previewOnly != null ||
      tradingEnabled != null ||
      realOrderSubmitted != null ||
      gptContext.hasDetails ||
      blockReasons.isNotEmpty;

  factory Candidate.fromJson(Map<String, dynamic> json,
      {String scoreKey = 'score', String noteKey = 'note'}) {
    final analysis = _readMap(json['analysis']);
    final readiness = _readMap(json['readiness']);
    final indicatorPayload = _readMap(json['indicator_payload'] ??
        json['indicators'] ??
        json['technical_snapshot'] ??
        analysis['indicator_payload']);
    final score = _readNullableInt(json[scoreKey]);
    final gptContext = GptRiskContext.fromJson(json['gpt_context']);
    final riskFlags = _dedupeStringList(
        _readStringList(json['risk_flags']) + gptContext.riskFlags);
    final gatingNotes = _dedupeStringList(
        _readStringList(json['gating_notes']) + gptContext.gatingNotes);
    final symbol = json['symbol']?.toString() ?? '';
    return Candidate(
      symbol: symbol,
      score: score,
      note: _readNullableString(json['note']) ??
          _readNullableString(json[noteKey]) ??
          '',
      entryReady: _readNullableBool(json['entry_ready']) ?? false,
      actionHint: _readNullableString(json['action_hint']) ?? 'watch',
      blockReason: _readNullableString(json['block_reason']),
      name: _companyName([
        json['company_name'],
        json['companyName'],
        json['name'],
        json['company'],
        json['display_name'],
        json['symbol_name'],
        json['korean_name'],
        json['asset_name'],
        _readMap(json['asset'])['name'],
        _readMap(json['profile'])['name'],
      ], symbol),
      provider: _readNullableString(json['provider']) ?? '',
      market: _readNullableString(json['market']) ?? '',
      marketLabel: _readNullableString(json['market_label']) ??
          _readNullableString(json['source_market_label']) ??
          '',
      currency: _readNullableString(json['currency']) ?? '',
      currentPrice: _readNullableDouble(json['current_price'] ??
          json['price'] ??
          analysis['current_price'] ??
          indicatorPayload['current_price'] ??
          indicatorPayload['price'] ??
          indicatorPayload['close']),
      indicatorStatus: _readNullableString(
              json['indicator_status'] ?? analysis['indicator_status']) ??
          '',
      indicatorBarCount: _readNullableInt(
          json['indicator_bar_count'] ?? analysis['indicator_bar_count']),
      indicatorPayload: indicatorPayload,
      effectiveMinEntryScore: _readNullableDouble(
          json['effective_min_entry_score'] ??
              readiness['effective_min_entry_score']),
      buySellSpread: _readNullableDouble(
          json['buy_sell_spread'] ?? readiness['buy_sell_spread']),
      entryScore:
          _readNullableDouble(json['entry_score'] ?? json['final_entry_score']),
      quantScore: _readNullableDouble(json['quant_score']),
      quantBuyScore: _readNullableDouble(json['quant_buy_score']),
      quantSellScore: _readNullableDouble(json['quant_sell_score']),
      aiBuyScore: _readNullableDouble(json['ai_buy_score']),
      aiSellScore: _readNullableDouble(json['ai_sell_score']),
      gptBuyScore:
          _readNullableDouble(json['gpt_buy_score']) ?? gptContext.gptBuyScore,
      gptSellScore: _readNullableDouble(json['gpt_sell_score']) ??
          gptContext.gptSellScore,
      finalEntryScore:
          _readNullableDouble(json['final_entry_score'] ?? json['entry_score']),
      finalScore: _readNullableDouble(json['final_score']),
      buyScore: _readNullableDouble(json['buy_score']),
      sellScore: _readNullableDouble(json['sell_score']),
      finalBuyScore: _readNullableDouble(json['final_buy_score']),
      finalSellScore: _readNullableDouble(json['final_sell_score']),
      confidence: _readNullableDouble(json['confidence']),
      action: _readNullableString(json['action']) ?? 'hold',
      result: _readNullableString(json['result']),
      status: _readNullableString(json['status']),
      skipReason: _readNullableString(json['skip_reason']),
      noOrderReason: _readNullableString(json['no_order_reason']),
      orderId: _readNullableString(json['order_id']),
      relatedOrderId: _readNullableString(json['related_order_id']),
      tradeAllowed: _readNullableBool(json['trade_allowed']),
      softEntryAllowed: _readNullableBool(json['soft_entry_allowed']),
      approvedByRisk: _readNullableBool(json['approved_by_risk']),
      hardBlocked: _readNullableBool(json['hard_blocked'] ??
              json['hard_block'] ??
              json['hard_block_new_buy']) ??
          gptContext.hardBlockNewBuy,
      hardBlockReason: _readNullableString(
          json['hard_block_reason'] ?? json['hard_block_new_buy_reason']),
      riskFlags: riskFlags,
      gatingNotes: gatingNotes,
      eventRiskLevel: json['event_risk_level']?.toString() ??
          _readMapString(json['event_risk'], 'risk_level') ??
          gptContext.eventRiskLevel,
      entryPenalty: _readNullableInt(json['entry_penalty']) ??
          _readNullableInt(json['entry_penalty_observed']) ??
          gptContext.entryPenalty,
      hardBlockNewBuy: _readNullableBool(json['hard_block_new_buy']) ??
          gptContext.hardBlockNewBuy,
      allowSellOrExit: _readNullableBool(json['allow_sell_or_exit']) ??
          gptContext.allowSellOrExit,
      gptContext: gptContext,
      reason: _readNullableString(json['reason']) ?? '',
      gptReason: _readNullableString(json['gpt_reason']) ?? '',
      marketResearchReason:
          _readNullableString(json['market_research_reason']) ?? '',
      gptUsed: _readNullableBool(json['gpt_used']),
      previewOnly: _readNullableBool(json['preview_only']),
      tradingEnabled: _readNullableBool(json['trading_enabled']),
      realOrderSubmitted: _readNullableBool(json['real_order_submitted']),
      warnings: _readStringList(json['warnings']),
      blockReasons: _readStringList(json['block_reasons']),
    );
  }
}

Map<String, dynamic> _readMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}



String _companyName(List<Object?> values, String symbol) {
  for (final value in values) {
    final text = _readNullableString(value);
    if (text == null) continue;
    if (symbol.isNotEmpty && text.toUpperCase() == symbol.toUpperCase()) {
      continue;
    }
    final lower = text.toLowerCase();
    if (lower == 'unknown company' || lower == 'unknown') continue;
    return text;
  }
  return symbol.isNotEmpty ? symbol : 'Unknown Company';
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

String? _readMapString(Object? value, String key) {
  if (value is Map<String, dynamic>) return value[key]?.toString();
  if (value is Map) return value[key]?.toString();
  return null;
}

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return int.tryParse(text) ?? double.tryParse(text)?.toInt();
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}

bool? _readNullableBool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return value.map((item) => item.toString()).toList();
}

List<String> _dedupeStringList(List<String> values) {
  final result = <String>[];
  for (final value in values) {
    final text = value.trim();
    if (text.isNotEmpty && !result.contains(text)) {
      result.add(text);
    }
  }
  return result;
}
