class KisExitShadowDecision {
  const KisExitShadowDecision({
    required this.status,
    required this.provider,
    required this.market,
    required this.mode,
    required this.decision,
    required this.action,
    required this.reason,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.realOrderSubmitAllowed,
    required this.autoSellEnabled,
    required this.schedulerRealOrderEnabled,
    required this.manualConfirmRequired,
    this.source = 'kis_exit_shadow_decision',
    this.sourceType = 'dry_run_sell_simulation',
    this.candidate,
    this.candidatesEvaluated = const [],
    this.checks = const {},
    this.safety = const {},
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.createdAt,
    this.checkedAt,
    this.runKey,
    this.runId,
  });

  factory KisExitShadowDecision.fromJson(Map<String, dynamic> json) {
    final candidate = _optionalMap(json['candidate']);
    final safety = _boolMap(json['safety']);
    return KisExitShadowDecision(
      status: _stringValue(json['status'], fallback: 'ok'),
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(json['mode'], fallback: 'shadow_exit_dry_run'),
      source:
          _stringValue(json['source'], fallback: 'kis_exit_shadow_decision'),
      sourceType: _stringValue(json['source_type'],
          fallback: 'dry_run_sell_simulation'),
      decision: _stringValue(json['decision'], fallback: 'hold'),
      action: _stringValue(json['action'], fallback: 'hold'),
      reason: _stringValue(json['reason'], fallback: ''),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ??
          safety['real_order_submitted'] ??
          false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ??
          safety['broker_submit_called'] ??
          false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ??
          safety['manual_submit_called'] ??
          false,
      realOrderSubmitAllowed: _boolValue(json['real_order_submit_allowed']) ??
          safety['real_order_submit_allowed'] ??
          false,
      autoSellEnabled: _boolValue(json['auto_sell_enabled']) ??
          safety['auto_sell_enabled'] ??
          false,
      schedulerRealOrderEnabled:
          _boolValue(json['scheduler_real_order_enabled']) ??
              safety['scheduler_real_order_enabled'] ??
              false,
      manualConfirmRequired: _boolValue(json['manual_confirm_required']) ??
          safety['manual_confirm_required'] ??
          true,
      candidate:
          candidate == null ? null : KisExitShadowCandidate.fromJson(candidate),
      candidatesEvaluated: _candidateList(json['candidates_evaluated']),
      checks: _boolMap(json['checks']),
      safety: safety,
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      createdAt: _nullableString(json['created_at']),
      checkedAt: _nullableString(json['checked_at']),
      runKey: _nullableString(_optionalMap(json['run'])?['run_key']),
      runId: _nullableInt(_optionalMap(json['run'])?['run_id']),
    );
  }

  final String status;
  final String provider;
  final String market;
  final String mode;
  final String source;
  final String sourceType;
  final String decision;
  final String action;
  final String reason;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool realOrderSubmitAllowed;
  final bool autoSellEnabled;
  final bool schedulerRealOrderEnabled;
  final bool manualConfirmRequired;
  final KisExitShadowCandidate? candidate;
  final List<KisExitShadowCandidate> candidatesEvaluated;
  final Map<String, bool> checks;
  final Map<String, bool> safety;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final String? createdAt;
  final String? checkedAt;
  final String? runKey;
  final int? runId;

  bool get isWouldSell => decision.trim().toLowerCase() == 'would_sell';
  bool get isManualReview => decision.trim().toLowerCase() == 'manual_review';
  bool get hasCandidate => candidate != null;

  bool check(String key) => checks[key] ?? false;
  bool safetyFlag(String key) => safety[key] ?? false;
}

class KisExitShadowCandidate {
  const KisExitShadowCandidate({
    required this.symbol,
    required this.side,
    required this.trigger,
    required this.triggerSource,
    required this.reason,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.realOrderSubmitAllowed,
    required this.manualConfirmRequired,
    this.quantityAvailable,
    this.suggestedQuantity,
    this.currentPrice,
    this.costBasis,
    this.currentValue,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.auditMetadata = const {},
  });

  factory KisExitShadowCandidate.fromJson(Map<String, dynamic> json) {
    return KisExitShadowCandidate(
      symbol: _stringValue(json['symbol'], fallback: ''),
      side: _stringValue(json['side'], fallback: 'sell').toLowerCase(),
      quantityAvailable: _nullableDouble(json['quantity_available']),
      suggestedQuantity: _nullableDouble(json['suggested_quantity']),
      trigger: _stringValue(json['trigger'], fallback: 'manual_review'),
      triggerSource:
          _stringValue(json['trigger_source'], fallback: 'manual_review'),
      currentPrice: _nullableDouble(json['current_price']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentValue: _nullableDouble(json['current_value']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      reason: _stringValue(json['reason'], fallback: ''),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      realOrderSubmitAllowed:
          _boolValue(json['real_order_submit_allowed']) ?? false,
      manualConfirmRequired:
          _boolValue(json['manual_confirm_required']) ?? true,
      auditMetadata: _dynamicMap(json['audit_metadata']),
    );
  }

  final String symbol;
  final String side;
  final double? quantityAvailable;
  final double? suggestedQuantity;
  final String trigger;
  final String triggerSource;
  final double? currentPrice;
  final double? costBasis;
  final double? currentValue;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final String reason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool realOrderSubmitAllowed;
  final bool manualConfirmRequired;
  final Map<String, dynamic> auditMetadata;

  bool get hasSafePlPct =>
      unrealizedPlPct != null && costBasis != null && costBasis! > 0;

  int? get suggestedQuantityInt {
    final value = suggestedQuantity ?? quantityAvailable;
    if (value == null || value < 1) return null;
    return value.floor();
  }
}

List<KisExitShadowCandidate> _candidateList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) =>
          KisExitShadowCandidate.fromJson(Map<String, dynamic>.from(item)))
      .where((item) => item.symbol.trim().isNotEmpty)
      .toList();
}

Map<String, bool> _boolMap(Object? value) {
  if (value is! Map) return const {};
  return Map<String, bool>.fromEntries(
    value.entries.map(
      (entry) => MapEntry(
        entry.key.toString(),
        _boolValue(entry.value) ?? false,
      ),
    ),
  );
}

Map<String, dynamic> _dynamicMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

Map<String, dynamic>? _optionalMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return null;
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

bool? _boolValue(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  final text = value.toString().trim().replaceAll(',', '');
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

List<String> _stringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}
