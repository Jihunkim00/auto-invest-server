class KisWatchlistPreview {
  const KisWatchlistPreview({
    required this.market,
    required this.provider,
    required this.currency,
    required this.dryRun,
    required this.previewOnly,
    required this.tradingEnabled,
    required this.gptAnalysisIncluded,
    required this.marketSession,
    required this.warnings,
    required this.configuredSymbolCount,
    required this.analyzedSymbolCount,
    required this.quantCandidatesCount,
    required this.researchedCandidatesCount,
    required this.finalBestCandidate,
    required this.bestScore,
    required this.shouldTrade,
    required this.action,
    required this.result,
    required this.reason,
    required this.count,
    required this.items,
  });

  factory KisWatchlistPreview.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'] as List<dynamic>? ?? const [];
    return KisWatchlistPreview(
      market: _readString(json['market'], 'KR'),
      provider: _readString(json['provider'], 'kis'),
      currency: _readString(json['currency'], 'KRW'),
      dryRun: json['dry_run'] == true,
      previewOnly: json['preview_only'] == true,
      tradingEnabled: json['trading_enabled'] == true,
      gptAnalysisIncluded: json['gpt_analysis_included'] == true,
      marketSession: Map<String, dynamic>.from(
          (json['market_session'] as Map?) ?? const {}),
      warnings: _readStringList(json['warnings']),
      configuredSymbolCount: _readInt(json['configured_symbol_count'], 0),
      analyzedSymbolCount: _readInt(json['analyzed_symbol_count'], 0),
      quantCandidatesCount: _readInt(json['quant_candidates_count'], 0),
      researchedCandidatesCount:
          _readInt(json['researched_candidates_count'], 0),
      finalBestCandidate: _readNullableString(json['final_best_candidate']),
      bestScore: _readNullableDouble(json['best_score']),
      shouldTrade: json['should_trade'] == true,
      action: _readString(json['action'], 'hold'),
      result: _readString(json['result'], 'preview_only'),
      reason: _readString(json['reason'], 'kr_trading_disabled'),
      count: _readInt(json['count'], rawItems.length),
      items: rawItems
          .whereType<Map>()
          .map((item) => KisWatchlistPreviewItem.fromJson(
              Map<String, dynamic>.from(item.cast<String, dynamic>())))
          .toList(),
    );
  }

  static const empty = KisWatchlistPreview(
    market: 'KR',
    provider: 'kis',
    currency: 'KRW',
    dryRun: true,
    previewOnly: true,
    tradingEnabled: false,
    gptAnalysisIncluded: false,
    marketSession: {},
    warnings: [],
    configuredSymbolCount: 0,
    analyzedSymbolCount: 0,
    quantCandidatesCount: 0,
    researchedCandidatesCount: 0,
    finalBestCandidate: null,
    bestScore: null,
    shouldTrade: false,
    action: 'hold',
    result: 'preview_only',
    reason: 'kr_trading_disabled',
    count: 0,
    items: [],
  );

  final String market;
  final String provider;
  final String currency;
  final bool dryRun;
  final bool previewOnly;
  final bool tradingEnabled;
  final bool gptAnalysisIncluded;
  final Map<String, dynamic> marketSession;
  final List<String> warnings;
  final int configuredSymbolCount;
  final int analyzedSymbolCount;
  final int quantCandidatesCount;
  final int researchedCandidatesCount;
  final String? finalBestCandidate;
  final double? bestScore;
  final bool shouldTrade;
  final String action;
  final String result;
  final String reason;
  final int count;
  final List<KisWatchlistPreviewItem> items;
}

class KisWatchlistPreviewItem {
  const KisWatchlistPreviewItem({
    required this.symbol,
    required this.name,
    required this.market,
    required this.currentPrice,
    required this.currency,
    required this.indicatorStatus,
    required this.indicatorPayload,
    required this.quantBuyScore,
    required this.quantSellScore,
    required this.aiBuyScore,
    required this.aiSellScore,
    required this.finalBuyScore,
    required this.finalSellScore,
    required this.confidence,
    required this.actionHint,
    required this.entryReady,
    required this.tradeAllowed,
    required this.blockReason,
    required this.reason,
    required this.gptReason,
    required this.riskFlags,
    required this.gatingNotes,
    required this.eventRisk,
    required this.dryRun,
    required this.previewOnly,
    required this.tradingEnabled,
    required this.realOrderSubmitted,
    required this.blockReasons,
    required this.warnings,
    required this.error,
  });

  factory KisWatchlistPreviewItem.fromJson(Map<String, dynamic> json) {
    return KisWatchlistPreviewItem(
      symbol: _readString(json['symbol'], ''),
      name: _readString(json['name'], ''),
      market: _readString(json['market'], ''),
      currentPrice: _readNullableDouble(json['current_price']),
      currency: _readString(json['currency'], 'KRW'),
      indicatorStatus:
          _readString(json['indicator_status'], 'insufficient_data'),
      indicatorPayload:
          Map<String, dynamic>.from((json['indicator_payload'] as Map?) ?? {}),
      quantBuyScore: _readNullableDouble(json['quant_buy_score']),
      quantSellScore: _readNullableDouble(json['quant_sell_score']),
      aiBuyScore: _readNullableDouble(json['ai_buy_score']),
      aiSellScore: _readNullableDouble(json['ai_sell_score']),
      finalBuyScore: _readNullableDouble(json['final_buy_score']),
      finalSellScore: _readNullableDouble(json['final_sell_score']),
      confidence: _readNullableDouble(json['confidence']),
      actionHint: _readString(json['action_hint'], 'watch'),
      entryReady: json['entry_ready'] == true,
      tradeAllowed: json['trade_allowed'] == true,
      blockReason: _readString(json['block_reason'], ''),
      reason: _readString(json['reason'], ''),
      gptReason: _readString(json['gpt_reason'], ''),
      riskFlags: _readStringList(json['risk_flags']),
      gatingNotes: _readStringList(json['gating_notes']),
      eventRisk: Map<String, dynamic>.from((json['event_risk'] as Map?) ?? {}),
      dryRun: json['dry_run'] == true,
      previewOnly: json['preview_only'] == true,
      tradingEnabled: json['trading_enabled'] == true,
      realOrderSubmitted: json['real_order_submitted'] == true,
      blockReasons: _readStringList(json['block_reasons']),
      warnings: _readStringList(json['warnings']),
      error: _readNullableString(json['error']),
    );
  }

  final String symbol;
  final String name;
  final String market;
  final double? currentPrice;
  final String currency;
  final String indicatorStatus;
  final Map<String, dynamic> indicatorPayload;
  final double? quantBuyScore;
  final double? quantSellScore;
  final double? aiBuyScore;
  final double? aiSellScore;
  final double? finalBuyScore;
  final double? finalSellScore;
  final double? confidence;
  final String actionHint;
  final bool entryReady;
  final bool tradeAllowed;
  final String blockReason;
  final String reason;
  final String gptReason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final Map<String, dynamic> eventRisk;
  final bool dryRun;
  final bool previewOnly;
  final bool tradingEnabled;
  final bool realOrderSubmitted;
  final List<String> blockReasons;
  final List<String> warnings;
  final String? error;

  bool get hasScores =>
      quantBuyScore != null ||
      quantSellScore != null ||
      aiBuyScore != null ||
      aiSellScore != null ||
      finalBuyScore != null ||
      finalSellScore != null ||
      confidence != null;

  bool get hasIndicatorValues =>
      indicatorPayload.values.any((value) => value != null);
}

int _readInt(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty) return null;
  return double.tryParse(text);
}

String _readString(Object? value, String fallback) {
  final text = value?.toString();
  if (text == null || text.isEmpty) return fallback;
  return text;
}

String? _readNullableString(Object? value) {
  final raw = value?.toString();
  if (raw == null) return null;
  final text = raw.trim();
  if (text.isEmpty) return null;
  return text;
}

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return value.map((item) => item.toString()).toList();
}
