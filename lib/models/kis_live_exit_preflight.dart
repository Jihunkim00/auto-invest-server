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
    this.status = 'ok',
    this.executionMode = 'manual_confirm_only',
    this.liveAutoEnabled = false,
    this.autoBuyEnabled = false,
    this.autoSellEnabled = false,
    this.realOrderSubmitAllowed = false,
    this.manualConfirmRequired = true,
    this.candidateCount = 0,
    this.candidates = const [],
    this.safety = const {},
    this.checkedAt,
    this.createdAt,
    this.runKey,
    this.runId,
    this.symbol,
    this.qty,
    this.estimatedNotional,
    this.estimatedPrice,
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
    final candidates = _candidateList(json);
    return KisLiveExitPreflightResult(
      status: _stringValue(json['status'], fallback: 'ok'),
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(json['mode'], fallback: 'kis_live_exit_preflight'),
      executionMode:
          _stringValue(json['execution_mode'], fallback: 'manual_confirm_only'),
      liveAutoEnabled: _boolValue(json['live_auto_enabled']) ?? false,
      autoBuyEnabled: _boolValue(json['auto_buy_enabled']) ?? false,
      autoSellEnabled: _boolValue(json['auto_sell_enabled']) ?? false,
      realOrderSubmitAllowed:
          _boolValue(json['real_order_submit_allowed']) ?? false,
      manualConfirmRequired:
          _boolValue(json['manual_confirm_required']) ?? true,
      candidateCount:
          _nullableInt(json['candidate_count']) ?? candidates.length,
      candidates: candidates,
      safety: _boolMap(json['safety']),
      checkedAt: _nullableString(json['checked_at']),
      createdAt: _nullableString(json['created_at']),
      runKey: _nullableString(_optionalMap(json['run'])?['run_key']),
      runId: _nullableInt(_optionalMap(json['run'])?['run_id']),
      action: _stringValue(json['action'], fallback: 'hold'),
      symbol: _nullableString(json['symbol']),
      qty: _nullableDouble(json['qty']),
      estimatedNotional: _nullableDouble(json['estimated_notional']),
      estimatedPrice: _nullableDouble(json['estimated_price']),
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

  final String status;
  final String provider;
  final String market;
  final String mode;
  final String executionMode;
  final bool liveAutoEnabled;
  final bool autoBuyEnabled;
  final bool autoSellEnabled;
  final bool realOrderSubmitAllowed;
  final bool manualConfirmRequired;
  final int candidateCount;
  final List<KisLiveExitCandidate> candidates;
  final Map<String, bool> safety;
  final String? checkedAt;
  final String? createdAt;
  final String? runKey;
  final int? runId;
  final String action;
  final String? symbol;
  final double? qty;
  final double? estimatedNotional;
  final double? estimatedPrice;
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

  bool safetyFlag(String key) => safety[key] ?? false;
}

class KisLiveExitCandidate {
  const KisLiveExitCandidate({
    required this.symbol,
    required this.side,
    required this.trigger,
    required this.triggerSource,
    required this.severity,
    required this.actionHint,
    required this.reason,
    required this.submitReady,
    required this.manualConfirmRequired,
    required this.realOrderSubmitAllowed,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.quantityAvailable,
    this.suggestedQuantity,
    this.currentPrice,
    this.estimatedNotional,
    this.costBasis,
    this.currentValue,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.riskFlags = const [],
    this.gatingNotes = const [],
  });

  factory KisLiveExitCandidate.fromJson(Map<String, dynamic> json) {
    return KisLiveExitCandidate(
      symbol: _stringValue(json['symbol'], fallback: ''),
      side: _stringValue(json['side'], fallback: 'sell').toLowerCase(),
      quantityAvailable: _nullableDouble(json['quantity_available']),
      suggestedQuantity: _nullableDouble(json['suggested_quantity']),
      currentPrice: _nullableDouble(json['current_price']),
      estimatedNotional: _nullableDouble(json['estimated_notional']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentValue: _nullableDouble(json['current_value']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      trigger: _stringValue(json['trigger'], fallback: 'manual_review'),
      triggerSource:
          _stringValue(json['trigger_source'], fallback: 'manual_review'),
      severity: _stringValue(json['severity'], fallback: 'review'),
      actionHint:
          _stringValue(json['action_hint'], fallback: 'manual_confirm_sell'),
      reason: _stringValue(json['reason'], fallback: ''),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      submitReady: _boolValue(json['submit_ready']) ?? false,
      manualConfirmRequired:
          _boolValue(json['manual_confirm_required']) ?? true,
      realOrderSubmitAllowed:
          _boolValue(json['real_order_submit_allowed']) ?? false,
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
    );
  }

  final String symbol;
  final String side;
  final double? quantityAvailable;
  final double? suggestedQuantity;
  final double? currentPrice;
  final double? estimatedNotional;
  final double? costBasis;
  final double? currentValue;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final String trigger;
  final String triggerSource;
  final String severity;
  final String actionHint;
  final String reason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final bool submitReady;
  final bool manualConfirmRequired;
  final bool realOrderSubmitAllowed;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;

  bool get hasSafePlPct =>
      unrealizedPlPct != null && costBasis != null && costBasis! > 0;

  int? get suggestedQuantityInt {
    final value = suggestedQuantity ?? quantityAvailable;
    if (value == null || value < 1) return null;
    return value.floor();
  }
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

List<KisLiveExitCandidate> _candidateList(Map<String, dynamic> json) {
  final raw = json['candidates'];
  if (raw is List) {
    final parsed = raw
        .whereType<Map>()
        .map((item) =>
            KisLiveExitCandidate.fromJson(Map<String, dynamic>.from(item)))
        .where((item) => item.symbol.trim().isNotEmpty)
        .toList();
    if (parsed.isNotEmpty) return parsed;
  }

  final action = _stringValue(json['action'], fallback: 'hold').toLowerCase();
  final symbol = _nullableString(json['symbol']);
  if (action != 'sell' || symbol == null) return const [];

  final reason =
      _stringValue(json['reason'], fallback: 'manual_review_required');
  return [
    KisLiveExitCandidate.fromJson({
      'symbol': symbol,
      'side': 'sell',
      'quantity_available': json['qty'],
      'suggested_quantity': json['qty'],
      'current_price': json['estimated_price'],
      'estimated_notional': json['estimated_notional'],
      'cost_basis': json['cost_basis'],
      'current_value': json['current_value'],
      'unrealized_pl': json['unrealized_pl'],
      'unrealized_pl_pct': json['unrealized_pl_pct'],
      'trigger': _triggerFromReason(reason),
      'trigger_source': json['exit_trigger_source'],
      'severity': 'review',
      'action_hint': 'manual_confirm_sell',
      'reason': json['message'] ?? reason,
      'risk_flags': json['risk_flags'],
      'gating_notes': json['gating_notes'],
      'submit_ready': false,
      'manual_confirm_required': json['manual_confirm_required'] ?? true,
      'real_order_submit_allowed': json['real_order_submit_allowed'] ?? false,
      'real_order_submitted': json['real_order_submitted'] ?? false,
      'broker_submit_called': json['broker_submit_called'] ?? false,
      'manual_submit_called': json['manual_submit_called'] ?? false,
    }),
  ];
}

String _triggerFromReason(String reason) {
  if (reason == 'stop_loss_triggered') return 'stop_loss';
  if (reason == 'take_profit_triggered') return 'take_profit';
  return 'manual_review';
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

Map<String, bool> _boolMap(Object? value) {
  if (value is! Map) return const {};
  return value
      .map((key, item) => MapEntry(key.toString(), _boolValue(item) ?? false));
}

Map<String, dynamic>? _optionalMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return null;
}

List<KisLiveExitReadinessCheck> _readinessList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) =>
          KisLiveExitReadinessCheck.fromJson(Map<String, dynamic>.from(item)))
      .toList();
}
