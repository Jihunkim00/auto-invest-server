class GptRiskContext {
  const GptRiskContext({
    this.marketRiskRegime,
    this.technicalMarketRegime,
    this.eventRiskLevel,
    this.fxRiskLevel,
    this.geopoliticalRiskLevel,
    this.energyRiskLevel,
    this.politicalRegulatoryRiskLevel,
    this.macroRiskLevel,
    this.sectorFundamentalTrend,
    this.revenueTrendContext,
    this.flowSignal,
    this.earningsRevisionSignal,
    this.valuationRiskLevel,
    this.entryPenalty,
    this.hardBlockNewBuy = false,
    this.allowSellOrExit = true,
    this.gptBuyScore,
    this.gptSellScore,
    this.affectedSectors = const [],
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.reason,
  });

  factory GptRiskContext.fromJson(Object? raw) {
    final json = _asMap(raw);
    if (json == null) return GptRiskContext.empty;
    return GptRiskContext(
      marketRiskRegime: _stringOrNull(json['market_risk_regime']),
      technicalMarketRegime: _stringOrNull(json['technical_market_regime']),
      eventRiskLevel: _stringOrNull(json['event_risk_level']),
      fxRiskLevel: _stringOrNull(json['fx_risk_level']),
      geopoliticalRiskLevel: _stringOrNull(json['geopolitical_risk_level']),
      energyRiskLevel: _stringOrNull(json['energy_risk_level']),
      politicalRegulatoryRiskLevel:
          _stringOrNull(json['political_regulatory_risk_level']),
      macroRiskLevel: _stringOrNull(json['macro_risk_level']),
      sectorFundamentalTrend: _stringOrNull(json['sector_fundamental_trend']),
      revenueTrendContext: _stringOrNull(json['revenue_trend_context']),
      flowSignal: _stringOrNull(json['flow_signal']),
      earningsRevisionSignal: _stringOrNull(json['earnings_revision_signal']),
      valuationRiskLevel: _stringOrNull(json['valuation_risk_level']),
      entryPenalty: _intOrNull(json['entry_penalty']),
      hardBlockNewBuy: _boolValue(json['hard_block_new_buy']) ?? false,
      allowSellOrExit: _boolValue(json['allow_sell_or_exit']) ?? true,
      gptBuyScore: _doubleOrNull(json['gpt_buy_score']),
      gptSellScore: _doubleOrNull(json['gpt_sell_score']),
      affectedSectors: _stringList(json['affected_sectors']),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      reason: _stringOrNull(json['reason']),
    );
  }

  static const empty = GptRiskContext();

  final String? marketRiskRegime;
  final String? technicalMarketRegime;
  final String? eventRiskLevel;
  final String? fxRiskLevel;
  final String? geopoliticalRiskLevel;
  final String? energyRiskLevel;
  final String? politicalRegulatoryRiskLevel;
  final String? macroRiskLevel;
  final String? sectorFundamentalTrend;
  final String? revenueTrendContext;
  final String? flowSignal;
  final String? earningsRevisionSignal;
  final String? valuationRiskLevel;
  final int? entryPenalty;
  final bool hardBlockNewBuy;
  final bool allowSellOrExit;
  final double? gptBuyScore;
  final double? gptSellScore;
  final List<String> affectedSectors;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final String? reason;

  bool get hasDetails =>
      marketRiskRegime != null ||
      technicalMarketRegime != null ||
      eventRiskLevel != null ||
      fxRiskLevel != null ||
      geopoliticalRiskLevel != null ||
      energyRiskLevel != null ||
      politicalRegulatoryRiskLevel != null ||
      macroRiskLevel != null ||
      sectorFundamentalTrend != null ||
      revenueTrendContext != null ||
      flowSignal != null ||
      earningsRevisionSignal != null ||
      valuationRiskLevel != null ||
      entryPenalty != null ||
      hardBlockNewBuy ||
      !allowSellOrExit ||
      gptBuyScore != null ||
      gptSellScore != null ||
      affectedSectors.isNotEmpty ||
      riskFlags.isNotEmpty ||
      gatingNotes.isNotEmpty ||
      reason != null;
}

Map<String, dynamic>? _asMap(Object? raw) {
  if (raw is Map<String, dynamic>) return raw;
  if (raw is Map) return Map<String, dynamic>.from(raw);
  return null;
}

String? _stringOrNull(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

int? _intOrNull(Object? value) {
  if (value is num) return value.toInt();
  final text = value?.toString().trim().replaceAll(',', '');
  if (text == null || text.isEmpty || text == 'null') return null;
  return int.tryParse(text) ?? double.tryParse(text)?.toInt();
}

double? _doubleOrNull(Object? value) {
  if (value is num) return value.toDouble();
  final text = value?.toString().trim().replaceAll(',', '');
  if (text == null || text.isEmpty || text == 'null') return null;
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
  if (value is List) {
    return value
        .map((item) => item.toString())
        .where((item) => item.trim().isNotEmpty)
        .toList();
  }
  if (value is String && value.trim().isNotEmpty && value != 'null') {
    return [value.trim()];
  }
  return const [];
}
