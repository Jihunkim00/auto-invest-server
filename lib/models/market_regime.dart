class MarketRegimeCondition {
  const MarketRegimeCondition({
    required this.key,
    required this.label,
    required this.passed,
    this.actual,
    this.rule,
  });

  final String key;
  final String label;
  final bool passed;
  final Object? actual;
  final String? rule;

  factory MarketRegimeCondition.fromJson(Map<String, dynamic> json) {
    return MarketRegimeCondition(
      key: _text(json['key']) ?? '',
      label: _text(json['label']) ?? '',
      passed: json['passed'] == true,
      actual: json['actual'],
      rule: _text(json['rule']),
    );
  }
}

class MarketRegimeTransition {
  const MarketRegimeTransition({
    this.passed = 0,
    this.total = 0,
    this.eligible = false,
    this.confirmed = false,
    this.streak = 0,
    this.requiredStreak = 2,
    this.conditions = const [],
    this.kospiTransition,
    this.combinedTransition,
  });

  final int passed;
  final int total;
  final bool eligible;
  final bool confirmed;
  final int streak;
  final int requiredStreak;
  final List<MarketRegimeCondition> conditions;
  final MarketRegimeTransition? kospiTransition;
  final MarketRegimeTransition? combinedTransition;

  factory MarketRegimeTransition.fromJson(Map<String, dynamic> json) {
    return MarketRegimeTransition(
      passed: _integer(json['passed']) ?? 0,
      total: _integer(json['total']) ?? 0,
      eligible: json['eligible'] == true,
      confirmed: json['confirmed'] == true,
      streak: _integer(json['streak']) ?? 0,
      requiredStreak: _integer(json['required_streak']) ?? 2,
      conditions: _conditionList(json['conditions']),
      kospiTransition: json['kospi_transition'] is Map
          ? MarketRegimeTransition.fromJson(
              Map<String, dynamic>.from(json['kospi_transition'] as Map),
            )
          : null,
      combinedTransition: json['combined_transition'] is Map
          ? MarketRegimeTransition.fromJson(
              Map<String, dynamic>.from(json['combined_transition'] as Map),
            )
          : null,
    );
  }
}

class MarketRegimeMarketData {
  const MarketRegimeMarketData({
    this.close,
    this.ema20,
    this.ema40,
    this.ema20FourWeekSlope,
    this.macdHistogram,
    this.rsi14,
    this.atr14,
    this.drawdown52w,
  });

  final double? close;
  final double? ema20;
  final double? ema40;
  final double? ema20FourWeekSlope;
  final double? macdHistogram;
  final double? rsi14;
  final double? atr14;
  final double? drawdown52w;

  factory MarketRegimeMarketData.fromJson(Map<String, dynamic> json) {
    return MarketRegimeMarketData(
      close: _number(json['close']),
      ema20: _number(json['ema20']),
      ema40: _number(json['ema40']),
      ema20FourWeekSlope: _number(json['ema20_4w_slope']),
      macdHistogram: _number(json['macd_histogram']),
      rsi14: _number(json['rsi14']),
      atr14: _number(json['atr14']),
      drawdown52w: _number(json['drawdown_52w']),
    );
  }
}

class MarketRegimeSource {
  const MarketRegimeSource({
    this.provider,
    this.symbol,
    this.label,
    this.timezone,
    this.weeklyBarCount,
    this.isProxy = false,
    this.error,
  });

  final String? provider;
  final String? symbol;
  final String? label;
  final String? timezone;
  final int? weeklyBarCount;
  final bool isProxy;
  final String? error;

  factory MarketRegimeSource.fromJson(Map<String, dynamic> json) {
    return MarketRegimeSource(
      provider: _text(json['provider']),
      symbol: _text(json['symbol']),
      label: _text(json['label']),
      timezone: _text(json['timezone']),
      weeklyBarCount: _integer(
        json['completed_weekly_bar_count'] ?? json['weekly_bar_count'],
      ),
      isProxy: json['is_proxy'] == true,
      error: _text(json['error']),
    );
  }
}

class MarketRegimeDataSource {
  const MarketRegimeDataSource({
    this.kospi,
    this.nasdaq,
    this.nasdaqIsProxy = false,
  });

  final MarketRegimeSource? kospi;
  final MarketRegimeSource? nasdaq;
  final bool nasdaqIsProxy;

  factory MarketRegimeDataSource.fromJson(Map<String, dynamic> json) {
    final kospiJson = _objectMap(json['kospi']);
    final nasdaqJson = _objectMap(json['nasdaq']);
    return MarketRegimeDataSource(
      kospi: kospiJson == null ? null : MarketRegimeSource.fromJson(kospiJson),
      nasdaq:
          nasdaqJson == null ? null : MarketRegimeSource.fromJson(nasdaqJson),
      nasdaqIsProxy:
          json['nasdaq_is_proxy'] == true || nasdaqJson?['is_proxy'] == true,
    );
  }
}

class MarketRegime {
  const MarketRegime({
    required this.status,
    this.stage,
    this.stageKey,
    this.stageLabel,
    this.shortLabel,
    this.summary,
    this.marketScore,
    this.scoreChange3w,
    this.kospiScore,
    this.nasdaqScore,
    this.kospiWeek,
    this.nasdaqWeek,
    this.confirmed = false,
    this.newBullishReversal = false,
    this.newBearishReversal = false,
    this.bullishTransition = const MarketRegimeTransition(),
    this.bearishTransition = const MarketRegimeTransition(),
    this.kospi = const MarketRegimeMarketData(),
    this.nasdaq = const MarketRegimeMarketData(),
    this.calculatedAt,
    this.nextScheduledCalculation,
    this.dataSource = const MarketRegimeDataSource(),
  });

  final String status;
  final int? stage;
  final String? stageKey;
  final String? stageLabel;
  final String? shortLabel;
  final String? summary;
  final double? marketScore;
  final double? scoreChange3w;
  final double? kospiScore;
  final double? nasdaqScore;
  final String? kospiWeek;
  final String? nasdaqWeek;
  final bool confirmed;
  final bool newBullishReversal;
  final bool newBearishReversal;
  final MarketRegimeTransition bullishTransition;
  final MarketRegimeTransition bearishTransition;
  final MarketRegimeMarketData kospi;
  final MarketRegimeMarketData nasdaq;
  final DateTime? calculatedAt;
  final DateTime? nextScheduledCalculation;
  final MarketRegimeDataSource dataSource;

  bool get hasStage => stage != null && stage! >= 1 && stage! <= 6;

  factory MarketRegime.fromJson(Map<String, dynamic> json) {
    final status = _text(json['status']);
    final stage = _integer(json['stage']);
    return MarketRegime(
      status:
          const {'confirmed', 'pending', 'insufficient_data'}.contains(status)
              ? status!
              : 'insufficient_data',
      stage: stage != null && stage >= 1 && stage <= 6 ? stage : null,
      stageKey: _text(json['stage_key']),
      stageLabel: _text(json['stage_label']),
      shortLabel: _text(json['short_label']),
      summary: _text(json['summary']),
      marketScore: _number(json['market_score']),
      scoreChange3w: _number(json['score_change_3w']),
      kospiScore: _number(json['kospi_score']),
      nasdaqScore: _number(json['nasdaq_score']),
      kospiWeek: _text(json['kospi_week']),
      nasdaqWeek: _text(json['nasdaq_week']),
      confirmed: json['confirmed'] == true,
      newBullishReversal: json['new_bullish_reversal'] == true,
      newBearishReversal: json['new_bearish_reversal'] == true,
      bullishTransition: MarketRegimeTransition.fromJson(
        _objectMap(json['bullish_transition']) ?? const {},
      ),
      bearishTransition: MarketRegimeTransition.fromJson(
        _objectMap(json['bearish_transition']) ?? const {},
      ),
      kospi: MarketRegimeMarketData.fromJson(
        _objectMap(json['kospi']) ?? const {},
      ),
      nasdaq: MarketRegimeMarketData.fromJson(
        _objectMap(json['nasdaq']) ?? const {},
      ),
      calculatedAt: _dateTime(json['calculated_at']),
      nextScheduledCalculation: _dateTime(json['next_scheduled_calculation']),
      dataSource: MarketRegimeDataSource.fromJson(
        _objectMap(json['data_source']) ?? const {},
      ),
    );
  }
}

List<MarketRegimeCondition> _conditionList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) =>
          MarketRegimeCondition.fromJson(Map<String, dynamic>.from(item)))
      .toList(growable: false);
}

Map<String, dynamic>? _objectMap(Object? value) {
  if (value is! Map) return null;
  return Map<String, dynamic>.from(value);
}

String? _text(Object? value) {
  if (value == null) return null;
  final text = value.toString().trim();
  return text.isEmpty ? null : text;
}

int? _integer(Object? value) {
  if (value is int) return value;
  if (value is num && value.isFinite) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

double? _number(Object? value) {
  if (value is num) return value.isFinite ? value.toDouble() : null;
  final result = double.tryParse(value?.toString() ?? '');
  return result != null && result.isFinite ? result : null;
}

DateTime? _dateTime(Object? value) {
  final text = _text(value);
  return text == null ? null : DateTime.tryParse(text);
}
