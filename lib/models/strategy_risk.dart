class StrategyRiskState {
  const StrategyRiskState({
    required this.provider,
    required this.market,
    required this.activeProfile,
    required this.monthlyTargetReturnPct,
    required this.monthlyTargetMinPct,
    required this.monthlyTargetMaxPct,
    required this.currentMonthReturnPct,
    required this.targetProgressPct,
    required this.targetHit,
    required this.monthlyMaxLossPct,
    required this.lossBudgetUsedPct,
    required this.monthlyLossLimitHit,
    required this.dailyMaxLossPct,
    required this.currentDailyReturnPct,
    required this.dailyLossLimitHit,
    required this.maxOrderNotionalPct,
    required this.maxOrderNotionalKrw,
    required this.recommendedOrderNotionalPct,
    required this.recommendedOrderNotionalKrw,
    required this.maxTradesPerDay,
    required this.tradesUsedToday,
    required this.tradesRemainingToday,
    required this.maxPositions,
    required this.currentPositionsCount,
    required this.newEntriesAllowed,
    required this.riskFlags,
    required this.gatingNotes,
    required this.dataQuality,
    required this.safety,
    this.primaryBlockReason,
  });

  final String provider;
  final String market;
  final String activeProfile;
  final double monthlyTargetReturnPct;
  final double monthlyTargetMinPct;
  final double monthlyTargetMaxPct;
  final double currentMonthReturnPct;
  final double targetProgressPct;
  final bool targetHit;
  final double monthlyMaxLossPct;
  final double lossBudgetUsedPct;
  final bool monthlyLossLimitHit;
  final double dailyMaxLossPct;
  final double currentDailyReturnPct;
  final bool dailyLossLimitHit;
  final double maxOrderNotionalPct;
  final double maxOrderNotionalKrw;
  final double recommendedOrderNotionalPct;
  final double recommendedOrderNotionalKrw;
  final int maxTradesPerDay;
  final int tradesUsedToday;
  final int tradesRemainingToday;
  final int maxPositions;
  final int currentPositionsCount;
  final bool newEntriesAllowed;
  final String? primaryBlockReason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final Map<String, dynamic> dataQuality;
  final Map<String, dynamic> safety;

  bool get sizeReduced => riskFlags.any(
        (flag) => flag.contains('size_reduced') || flag.contains('capped'),
      );

  bool get lossLimitHit => monthlyLossLimitHit || dailyLossLimitHit;

  factory StrategyRiskState.fromJson(Map<String, dynamic> json) {
    return StrategyRiskState(
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      activeProfile: _string(json['active_profile'], 'safe'),
      monthlyTargetReturnPct: _double(json['monthly_target_return_pct']),
      monthlyTargetMinPct: _double(json['monthly_target_min_pct']),
      monthlyTargetMaxPct: _double(json['monthly_target_max_pct']),
      currentMonthReturnPct: _double(json['current_month_return_pct']),
      targetProgressPct: _double(json['target_progress_pct']),
      targetHit: json['target_hit'] == true,
      monthlyMaxLossPct: _double(json['monthly_max_loss_pct']),
      lossBudgetUsedPct: _double(json['loss_budget_used_pct']),
      monthlyLossLimitHit: json['monthly_loss_limit_hit'] == true,
      dailyMaxLossPct: _double(json['daily_max_loss_pct']),
      currentDailyReturnPct: _double(json['current_daily_return_pct']),
      dailyLossLimitHit: json['daily_loss_limit_hit'] == true,
      maxOrderNotionalPct: _double(json['max_order_notional_pct']),
      maxOrderNotionalKrw: _double(json['max_order_notional_krw']),
      recommendedOrderNotionalPct:
          _double(json['recommended_order_notional_pct']),
      recommendedOrderNotionalKrw:
          _double(json['recommended_order_notional_krw']),
      maxTradesPerDay: _int(json['max_trades_per_day']),
      tradesUsedToday: _int(json['trades_used_today']),
      tradesRemainingToday: _int(json['trades_remaining_today']),
      maxPositions: _int(json['max_positions']),
      currentPositionsCount: _int(json['current_positions_count']),
      newEntriesAllowed: json['new_entries_allowed'] == true,
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      dataQuality: _map(json['data_quality']),
      safety: _map(json['safety']),
    );
  }
}

double _double(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? 0;
}

int _int(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

String _string(Object? value, String fallback) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? fallback : text;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty || text == 'null' ? null : text;
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item?.toString().trim().isNotEmpty == true) item.toString().trim(),
  ];
}

Map<String, dynamic> _map(Object? value) {
  return value is Map ? Map<String, dynamic>.from(value) : const {};
}
