class StrategyLiveAutoExitCandidate {
  const StrategyLiveAutoExitCandidate({
    required this.symbol,
    required this.quantity,
    required this.trigger,
    required this.reason,
    required this.eligible,
    required this.riskFlags,
    required this.gatingNotes,
    required this.dataQuality,
    this.symbolName,
    this.currentPrice,
    this.costBasis,
    this.currentValue,
    this.unrealizedPnl,
    this.unrealizedPnlPct,
    this.stopLossPct,
    this.takeProfitPct,
    this.positionAgeDays,
    this.maxHoldingDays,
    this.blockReason,
  });

  final String symbol;
  final String? symbolName;
  final int quantity;
  final double? currentPrice;
  final double? costBasis;
  final double? currentValue;
  final double? unrealizedPnl;
  final double? unrealizedPnlPct;
  final double? stopLossPct;
  final double? takeProfitPct;
  final double? positionAgeDays;
  final int? maxHoldingDays;
  final String trigger;
  final String reason;
  final bool eligible;
  final String? blockReason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final Map<String, dynamic> dataQuality;

  factory StrategyLiveAutoExitCandidate.fromJson(Map<String, dynamic> json) {
    return StrategyLiveAutoExitCandidate(
      symbol: _string(json['symbol'], '-'),
      symbolName: _nullableString(json['symbol_name']),
      quantity: _int(json['quantity']),
      currentPrice: _nullableDouble(json['current_price']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentValue: _nullableDouble(json['current_value']),
      unrealizedPnl: _nullableDouble(json['unrealized_pnl']),
      unrealizedPnlPct: _nullableDouble(json['unrealized_pnl_pct']),
      stopLossPct: _nullableDouble(json['stop_loss_pct']),
      takeProfitPct: _nullableDouble(json['take_profit_pct']),
      positionAgeDays: _nullableDouble(json['position_age_days']),
      maxHoldingDays: _nullableInt(json['max_holding_days']),
      trigger: _string(json['trigger'], 'none'),
      reason: _string(json['reason'], 'no_exit_trigger'),
      eligible: json['eligible'] == true,
      blockReason: _nullableString(json['block_reason']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      dataQuality: _map(json['data_quality']),
    );
  }
}

class StrategyLiveAutoExitReadiness {
  const StrategyLiveAutoExitReadiness({
    required this.enabled,
    required this.ready,
    required this.provider,
    required this.market,
    required this.dryRun,
    required this.killSwitch,
    required this.kisEnabled,
    required this.kisRealOrderEnabled,
    required this.schedulerLiveEnabled,
    required this.positionsCount,
    required this.candidateCount,
    required this.maxOrdersPerDay,
    required this.ordersUsedToday,
    required this.ordersRemainingToday,
    required this.checks,
    required this.candidates,
    required this.riskFlags,
    required this.gatingNotes,
    required this.safety,
    this.activeProfile,
    this.allowedProfiles = const [],
    this.selectedSymbol,
    this.selectedTrigger,
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
  final int positionsCount;
  final int candidateCount;
  final String? selectedSymbol;
  final String? selectedTrigger;
  final int maxOrdersPerDay;
  final int ordersUsedToday;
  final int ordersRemainingToday;
  final String? primaryBlockReason;
  final List<Map<String, dynamic>> checks;
  final List<StrategyLiveAutoExitCandidate> candidates;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final Map<String, dynamic> safety;

  factory StrategyLiveAutoExitReadiness.fromJson(Map<String, dynamic> json) {
    final rawCandidates = json['candidates'];
    return StrategyLiveAutoExitReadiness(
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
      positionsCount: _int(json['positions_count']),
      candidateCount: _int(json['candidate_count']),
      selectedSymbol: _nullableString(json['selected_symbol']),
      selectedTrigger: _nullableString(json['selected_trigger']),
      maxOrdersPerDay: _int(json['max_orders_per_day']),
      ordersUsedToday: _int(json['orders_used_today']),
      ordersRemainingToday: _int(json['orders_remaining_today']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      checks: _maps(json['checks']),
      candidates: rawCandidates is List
          ? [
              for (final item in rawCandidates)
                if (item is Map)
                  StrategyLiveAutoExitCandidate.fromJson(
                    Map<String, dynamic>.from(item),
                  ),
            ]
          : const [],
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      safety: _map(json['safety']),
    );
  }
}

class StrategyLiveAutoExitRunResult {
  const StrategyLiveAutoExitRunResult({
    required this.status,
    required this.action,
    required this.provider,
    required this.market,
    required this.submitted,
    required this.riskFlags,
    required this.gatingNotes,
    required this.safety,
    this.activeProfile,
    this.symbol,
    this.symbolName,
    this.exitTrigger,
    this.exitReason,
    this.quantity,
    this.currentPrice,
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
  final String? exitTrigger;
  final String? exitReason;
  final bool submitted;
  final int? quantity;
  final double? currentPrice;
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

  factory StrategyLiveAutoExitRunResult.fromJson(Map<String, dynamic> json) {
    return StrategyLiveAutoExitRunResult(
      status: _string(json['status'], 'blocked'),
      action: _string(json['action'], 'blocked'),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      activeProfile: _nullableString(json['active_profile']),
      symbol: _nullableString(json['symbol']),
      symbolName: _nullableString(json['symbol_name']),
      exitTrigger: _nullableString(json['exit_trigger']),
      exitReason: _nullableString(json['exit_reason']),
      submitted: json['submitted'] == true,
      quantity: _nullableInt(json['quantity']),
      currentPrice: _nullableDouble(json['current_price']),
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

class StrategyLiveAutoExitRecent {
  const StrategyLiveAutoExitRecent({
    required this.provider,
    required this.market,
    required this.items,
    required this.safety,
  });

  final String provider;
  final String market;
  final List<StrategyLiveAutoExitRunResult> items;
  final Map<String, dynamic> safety;

  StrategyLiveAutoExitRunResult? get latest =>
      items.isEmpty ? null : items.first;

  factory StrategyLiveAutoExitRecent.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    return StrategyLiveAutoExitRecent(
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      items: rawItems is List
          ? [
              for (final item in rawItems)
                if (item is Map)
                  StrategyLiveAutoExitRunResult.fromJson(
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
