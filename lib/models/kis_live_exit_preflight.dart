class KisLiveExitPreflightResult {
  const KisLiveExitPreflightResult({
    required this.provider,
    required this.market,
    required this.mode,
    required this.action,
    required this.reason,
    required this.wouldSubmitIfEnabled,
    required this.liveOrderSubmitted,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.symbol,
    this.qty,
    this.estimatedNotional,
    this.costBasis,
    this.currentValue,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.takeProfitThresholdPct,
    this.stopLossThresholdPct,
    this.exitTriggerSource,
    this.message,
    this.result,
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.blockedBy = const [],
    this.readinessChecks = const [],
  });

  factory KisLiveExitPreflightResult.fromJson(Map<String, dynamic> json) {
    return KisLiveExitPreflightResult(
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(json['mode'], fallback: 'kis_live_exit_preflight'),
      action: _stringValue(json['action'], fallback: 'hold'),
      symbol: _nullableString(json['symbol']),
      qty: _nullableDouble(json['qty']),
      estimatedNotional: _nullableDouble(json['estimated_notional']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentValue: _nullableDouble(json['current_value']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      takeProfitThresholdPct:
          _nullableDouble(json['take_profit_threshold_pct']),
      stopLossThresholdPct: _nullableDouble(json['stop_loss_threshold_pct']),
      exitTriggerSource: _nullableString(json['exit_trigger_source']),
      reason: _stringValue(json['reason'], fallback: ''),
      message: _nullableString(json['message']),
      result: _nullableString(json['result']),
      wouldSubmitIfEnabled:
          _boolValue(json['would_submit_if_enabled']) ?? false,
      liveOrderSubmitted: _boolValue(json['live_order_submitted']) ?? false,
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      blockedBy: _stringList(json['blocked_by']),
      readinessChecks: _readinessList(json['readiness_checks']),
    );
  }

  final String provider;
  final String market;
  final String mode;
  final String action;
  final String? symbol;
  final double? qty;
  final double? estimatedNotional;
  final double? costBasis;
  final double? currentValue;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final double? takeProfitThresholdPct;
  final double? stopLossThresholdPct;
  final String? exitTriggerSource;
  final String reason;
  final String? message;
  final String? result;
  final bool wouldSubmitIfEnabled;
  final bool liveOrderSubmitted;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<String> blockedBy;
  final List<KisLiveExitReadinessCheck> readinessChecks;

  bool get hasHeldPosition => symbol != null && symbol!.trim().isNotEmpty;
  bool get isSellCandidate => action.trim().toLowerCase() == 'sell';
}

class KisLiveExitReadinessCheck {
  const KisLiveExitReadinessCheck({
    required this.name,
    required this.passed,
    this.reason,
  });

  factory KisLiveExitReadinessCheck.fromJson(Map<String, dynamic> json) {
    return KisLiveExitReadinessCheck(
      name: _stringValue(json['name'], fallback: ''),
      passed: _boolValue(json['passed']) ?? false,
      reason: _nullableString(json['reason']),
    );
  }

  final String name;
  final bool passed;
  final String? reason;
}

String _stringValue(Object? value, {required String fallback}) {
  final text = value?.toString();
  if (text == null || text.isEmpty || text == 'null') return fallback;
  return text;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
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

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}

List<String> _stringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}

List<KisLiveExitReadinessCheck> _readinessList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) =>
          KisLiveExitReadinessCheck.fromJson(Map<String, dynamic>.from(item)))
      .toList();
}
