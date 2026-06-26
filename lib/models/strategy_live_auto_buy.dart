class StrategyLiveAutoBuyReadiness {
  const StrategyLiveAutoBuyReadiness({
    required this.enabled,
    required this.ready,
    required this.provider,
    required this.market,
    required this.dryRun,
    required this.killSwitch,
    required this.kisEnabled,
    required this.kisRealOrderEnabled,
    required this.schedulerLiveEnabled,
    required this.recentDryRunRequired,
    required this.recentDryRunFound,
    required this.recentDryRunTtlMinutes,
    required this.maxOrdersPerDay,
    required this.ordersUsedToday,
    required this.ordersRemainingToday,
    required this.maxNotionalKrw,
    required this.maxNotionalPct,
    required this.checks,
    required this.riskFlags,
    required this.gatingNotes,
    required this.safety,
    this.activeProfile,
    this.allowedProfiles = const [],
    this.recentDryRunAgeMinutes,
    this.selectedSymbol,
    this.primaryBlockReason,
  });

  final bool enabled;
  final bool ready;
  final String provider;
  final String market;
  final String? activeProfile;
  final List<String> allowedProfiles;
  final bool dryRun;
  final bool killSwitch;
  final bool kisEnabled;
  final bool kisRealOrderEnabled;
  final bool schedulerLiveEnabled;
  final bool recentDryRunRequired;
  final bool recentDryRunFound;
  final double? recentDryRunAgeMinutes;
  final int recentDryRunTtlMinutes;
  final String? selectedSymbol;
  final int maxOrdersPerDay;
  final int ordersUsedToday;
  final int ordersRemainingToday;
  final double maxNotionalKrw;
  final double maxNotionalPct;
  final String? primaryBlockReason;
  final List<Map<String, dynamic>> checks;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final Map<String, dynamic> safety;

  factory StrategyLiveAutoBuyReadiness.fromJson(Map<String, dynamic> json) {
    return StrategyLiveAutoBuyReadiness(
      enabled: json['enabled'] == true,
      ready: json['ready'] == true,
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      activeProfile: _nullableString(json['active_profile']),
      allowedProfiles: _strings(json['allowed_profiles']),
      dryRun: json['dry_run'] == true,
      killSwitch: json['kill_switch'] == true,
      kisEnabled: json['kis_enabled'] == true,
      kisRealOrderEnabled: json['kis_real_order_enabled'] == true,
      schedulerLiveEnabled: json['scheduler_live_enabled'] == true,
      recentDryRunRequired: json['recent_dry_run_required'] == true,
      recentDryRunFound: json['recent_dry_run_found'] == true,
      recentDryRunAgeMinutes:
          _nullableDouble(json['recent_dry_run_age_minutes']),
      recentDryRunTtlMinutes: _int(json['recent_dry_run_ttl_minutes']),
      selectedSymbol: _nullableString(json['selected_symbol']),
      maxOrdersPerDay: _int(json['max_orders_per_day']),
      ordersUsedToday: _int(json['orders_used_today']),
      ordersRemainingToday: _int(json['orders_remaining_today']),
      maxNotionalKrw: _double(json['max_notional_krw']),
      maxNotionalPct: _double(json['max_notional_pct']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      checks: _maps(json['checks']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      safety: _map(json['safety']),
    );
  }
}

class StrategyLiveAutoBuyRunResult {
  const StrategyLiveAutoBuyRunResult({
    required this.status,
    required this.action,
    required this.provider,
    required this.market,
    required this.targetRiskApproved,
    required this.validationApproved,
    required this.submitted,
    required this.riskFlags,
    required this.gatingNotes,
    required this.safety,
    this.activeProfile,
    this.symbol,
    this.symbolName,
    this.sourceDryRunId,
    this.sourceSignalId,
    this.sourceTradeRunId,
    this.promotionId,
    this.promotionTrace = const {},
    this.quantity,
    this.estimatedPrice,
    this.submittedNotionalKrw,
    this.relatedOrderId,
    this.brokerOrderId,
    this.brokerStatus,
    this.internalStatus,
    this.blockReason,
    this.attemptId,
    this.signalId,
    this.tradeRunId,
    this.createdAt,
  });

  final String status;
  final String action;
  final String provider;
  final String market;
  final String? activeProfile;
  final String? symbol;
  final String? symbolName;
  final int? sourceDryRunId;
  final int? sourceSignalId;
  final int? sourceTradeRunId;
  final int? promotionId;
  final Map<String, dynamic> promotionTrace;
  final bool targetRiskApproved;
  final bool validationApproved;
  final bool submitted;
  final int? quantity;
  final double? estimatedPrice;
  final double? submittedNotionalKrw;
  final int? relatedOrderId;
  final String? brokerOrderId;
  final String? brokerStatus;
  final String? internalStatus;
  final String? blockReason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final int? attemptId;
  final int? signalId;
  final int? tradeRunId;
  final DateTime? createdAt;
  final Map<String, dynamic> safety;

  bool get blocked => action == 'blocked' || blockReason != null;
  bool get syncRequired => status == 'sync_required';

  factory StrategyLiveAutoBuyRunResult.fromJson(Map<String, dynamic> json) {
    return StrategyLiveAutoBuyRunResult(
      status: _string(json['status'], 'blocked'),
      action: _string(json['action'], 'blocked'),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      activeProfile: _nullableString(json['active_profile']),
      symbol: _nullableString(json['symbol']),
      symbolName: _nullableString(json['symbol_name']),
      sourceDryRunId: _nullableInt(json['source_dry_run_id']),
      sourceSignalId: _nullableInt(json['source_signal_id']),
      sourceTradeRunId: _nullableInt(json['source_trade_run_id']),
      promotionId: _nullableInt(json['promotion_id']),
      promotionTrace: _map(json['promotion_trace']),
      targetRiskApproved: json['target_risk_approved'] == true,
      validationApproved: json['validation_approved'] == true,
      submitted: json['submitted'] == true,
      quantity: _nullableInt(json['quantity']),
      estimatedPrice: _nullableDouble(json['estimated_price']),
      submittedNotionalKrw: _nullableDouble(json['submitted_notional_krw']),
      relatedOrderId: _nullableInt(json['related_order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      brokerStatus: _nullableString(json['broker_status']),
      internalStatus: _nullableString(json['internal_status']),
      blockReason: _nullableString(json['block_reason']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      attemptId: _nullableInt(json['attempt_id']),
      signalId: _nullableInt(json['signal_id']),
      tradeRunId: _nullableInt(json['trade_run_id']),
      createdAt: _dateTime(json['created_at']),
      safety: _map(json['safety']),
    );
  }
}

class StrategyLiveAutoBuyRecent {
  const StrategyLiveAutoBuyRecent({
    required this.provider,
    required this.market,
    required this.items,
    required this.safety,
  });

  final String provider;
  final String market;
  final List<StrategyLiveAutoBuyRunResult> items;
  final Map<String, dynamic> safety;

  StrategyLiveAutoBuyRunResult? get latest =>
      items.isEmpty ? null : items.first;

  factory StrategyLiveAutoBuyRecent.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    return StrategyLiveAutoBuyRecent(
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      items: rawItems is List
          ? [
              for (final item in rawItems)
                if (item is Map)
                  StrategyLiveAutoBuyRunResult.fromJson(
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
