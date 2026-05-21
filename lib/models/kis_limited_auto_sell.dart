class KisLimitedAutoSellCandidate {
  const KisLimitedAutoSellCandidate({
    required this.symbol,
    required this.name,
    required this.quantity,
    required this.currentPrice,
    required this.averagePrice,
    required this.costBasis,
    required this.currentValue,
    required this.unrealizedPl,
    required this.unrealizedPlPct,
    required this.stopLossThresholdPct,
    required this.takeProfitThresholdPct,
    required this.stopLossTriggered,
    required this.takeProfitTriggered,
    required this.takeProfitReadinessOnly,
    required this.takeProfitActionable,
    required this.takeProfitExecutionDisabled,
    required this.weakTrendTriggered,
    required this.sellPressureTriggered,
    required this.status,
    required this.exitReason,
    required this.reason,
    required this.riskFlags,
    required this.gatingNotes,
    required this.blockReasons,
    required this.latestOrder,
    required this.rawPayload,
  });

  factory KisLimitedAutoSellCandidate.fromJson(Map<String, dynamic> json) {
    return KisLimitedAutoSellCandidate(
      symbol: _stringValue(json['symbol'], fallback: ''),
      name: _stringValue(
        json['company_name'] ?? json['name'],
        fallback: 'Unknown company',
      ),
      quantity: _nullableInt(
        json['quantity'] ?? json['suggested_quantity'] ?? json['qty'],
      ),
      currentPrice: _nullableDouble(json['current_price']),
      averagePrice:
          _nullableDouble(json['average_price'] ?? json['avg_entry_price']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentValue:
          _nullableDouble(json['current_value'] ?? json['market_value']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      stopLossThresholdPct: _nullableDouble(json['stop_loss_threshold_pct']),
      takeProfitThresholdPct:
          _nullableDouble(json['take_profit_threshold_pct']),
      stopLossTriggered: _boolValue(json['stop_loss_triggered']) ?? false,
      takeProfitTriggered: _boolValue(json['take_profit_triggered']) ?? false,
      takeProfitReadinessOnly: _boolValue(json['take_profit_readiness_only']) ??
          (_boolValue(json['take_profit_triggered']) ?? false),
      takeProfitActionable: _boolValue(json['take_profit_actionable']) ?? false,
      takeProfitExecutionDisabled:
          _boolValue(json['take_profit_execution_disabled']) ??
              (_boolValue(json['take_profit_triggered']) ?? false),
      weakTrendTriggered: _boolValue(json['weak_trend_triggered']) ?? false,
      sellPressureTriggered:
          _boolValue(json['sell_pressure_triggered']) ?? false,
      status: _stringValue(
        json['status'] ?? json['holding_status'],
        fallback: 'HOLD',
      ),
      exitReason: _stringValue(json['exit_reason'], fallback: ''),
      reason: _stringValue(
        json['reason'] ?? json['human_reason'] ?? json['exit_reason'],
        fallback: '',
      ),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      blockReasons: _stringList(json['block_reasons'] ?? json['blocked_by']),
      latestOrder: _dynamicMap(
        json['latest_order'] ?? json['latest_related_sell_order'],
      ),
      rawPayload: _dynamicMap(json),
    );
  }

  final String symbol;
  final String name;
  final int? quantity;
  final double? currentPrice;
  final double? averagePrice;
  final double? costBasis;
  final double? currentValue;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final double? stopLossThresholdPct;
  final double? takeProfitThresholdPct;
  final bool stopLossTriggered;
  final bool takeProfitTriggered;
  final bool takeProfitReadinessOnly;
  final bool takeProfitActionable;
  final bool takeProfitExecutionDisabled;
  final bool weakTrendTriggered;
  final bool sellPressureTriggered;
  final String status;
  final String exitReason;
  final String reason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<String> blockReasons;
  final Map<String, dynamic> latestOrder;
  final Map<String, dynamic> rawPayload;
}

class KisLimitedAutoSell {
  const KisLimitedAutoSell({
    required this.status,
    required this.provider,
    required this.market,
    required this.mode,
    required this.source,
    required this.sourceType,
    required this.result,
    required this.action,
    required this.reason,
    required this.humanReadableStatus,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.autoBuyEnabled,
    required this.autoSellEnabled,
    required this.schedulerRealOrderEnabled,
    required this.liveAutoSellEnabled,
    required this.stopLossAutoSellEnabled,
    required this.takeProfitAutoSellEnabled,
    required this.schedulerRealOrdersEnabled,
    required this.dryRun,
    required this.killSwitch,
    required this.kisEnabled,
    required this.kisRealOrderEnabled,
    required this.marketOpen,
    required this.sellSessionAllowed,
    required this.autoOrderReady,
    required this.realOrderSubmitAllowed,
    required this.stopLossExecutionEnabled,
    required this.takeProfitReadinessEnabled,
    required this.takeProfitExecutionEnabled,
    required this.takeProfitNonActionable,
    required this.takeProfitActionable,
    required this.takeProfitReadinessOnly,
    required this.takeProfitExecutionDisabled,
    required this.stopLossTriggered,
    required this.takeProfitTriggered,
    required this.weakTrendTriggered,
    required this.sellPressureTriggered,
    required this.candidateCount,
    required this.candidates,
    required this.checks,
    required this.safety,
    required this.dailyLimit,
    required this.duplicateOrderCheck,
    required this.auditMetadata,
    required this.diagnostics,
    required this.rawPayload,
    this.finalCandidate,
    this.symbol,
    this.quantity,
    this.trigger,
    this.triggerSource,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    this.createdAt,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.costBasis,
    this.currentValue,
    this.currentPrice,
    this.notional,
    this.stopLossThresholdPct,
    this.takeProfitThresholdPct,
    this.primaryBlockReason,
    this.dailyLimitRemaining,
    this.validationStatus = '',
    this.readinessLabels = const [],
    this.blockReasons = const [],
    this.blockedBy = const [],
    this.failedChecks = const [],
  });

  factory KisLimitedAutoSell.fromJson(Map<String, dynamic> json) {
    final candidates = _candidateList(json['candidates']);
    final finalCandidateMap = _dynamicMap(json['final_candidate']);
    final finalCandidate = finalCandidateMap.isNotEmpty
        ? KisLimitedAutoSellCandidate.fromJson(finalCandidateMap)
        : _legacyCandidate(json);
    final checks = _dynamicMap(json['checks']);
    final safety = _dynamicMap(json['safety']);
    final dailyLimit = _dynamicMap(json['daily_limit']);
    final duplicateOrderCheck = _dynamicMap(json['duplicate_order_check']);
    return KisLimitedAutoSell(
      status: _stringValue(json['status'], fallback: 'ok'),
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(
        json['mode'],
        fallback: 'kis_limited_auto_stop_loss_run',
      ),
      source: _stringValue(
        json['source'],
        fallback: 'kis_limited_auto_stop_loss',
      ),
      sourceType: _stringValue(json['source_type'], fallback: ''),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      reason: _stringValue(json['reason'], fallback: ''),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      humanReadableStatus: _stringValue(
        json['human_readable_status'] ?? json['message'],
        fallback: '',
      ),
      symbol: _nullableString(json['symbol']),
      quantity: _nullableInt(json['quantity'] ?? json['qty']),
      trigger: _nullableString(json['trigger'] ?? json['exit_trigger']),
      triggerSource: _nullableString(
        json['trigger_source_detail'] ??
            json['trigger_source'] ??
            json['exit_trigger_source'],
      ),
      orderId: _nullableInt(json['order_id'] ?? json['order_log_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      autoBuyEnabled: _boolValue(json['auto_buy_enabled']) ??
          _boolValue(json['live_auto_buy_enabled']) ??
          false,
      autoSellEnabled: _boolValue(json['auto_sell_enabled']) ??
          _boolValue(json['live_auto_sell_enabled']) ??
          false,
      schedulerRealOrderEnabled:
          _boolValue(json['scheduler_real_order_enabled']) ??
              _boolValue(json['scheduler_real_orders_enabled']) ??
              false,
      liveAutoSellEnabled: _boolValue(json['live_auto_sell_enabled']) ?? false,
      stopLossAutoSellEnabled:
          _boolValue(json['stop_loss_auto_sell_enabled']) ??
              _boolValue(json['kis_limited_auto_stop_loss_enabled']) ??
              false,
      takeProfitAutoSellEnabled:
          _boolValue(json['take_profit_auto_sell_enabled']) ?? false,
      schedulerRealOrdersEnabled:
          _boolValue(json['scheduler_real_orders_enabled']) ?? false,
      dryRun:
          _boolValue(json['dry_run']) ?? _boolValue(checks['dry_run']) ?? true,
      killSwitch: _boolValue(json['kill_switch']) ??
          _boolValue(checks['kill_switch']) ??
          false,
      kisEnabled: _boolValue(json['kis_enabled']) ??
          _boolValue(checks['kis_enabled']) ??
          false,
      kisRealOrderEnabled: _boolValue(json['kis_real_order_enabled']) ??
          _boolValue(checks['kis_real_order_enabled']) ??
          false,
      marketOpen: _boolValue(json['market_open']) ??
          _boolValue(checks['market_open']) ??
          false,
      sellSessionAllowed: _boolValue(json['sell_session_allowed']) ??
          _boolValue(checks['sell_session_allowed']) ??
          false,
      autoOrderReady: _boolValue(json['auto_order_ready']) ?? false,
      realOrderSubmitAllowed:
          _boolValue(json['real_order_submit_allowed']) ?? false,
      stopLossExecutionEnabled:
          _boolValue(json['stop_loss_execution_enabled']) ?? false,
      takeProfitReadinessEnabled:
          _boolValue(json['take_profit_readiness_enabled']) ??
              _boolValue(safety['take_profit_readiness_enabled']) ??
              false,
      takeProfitExecutionEnabled:
          _boolValue(json['take_profit_execution_enabled']) ??
              _boolValue(safety['take_profit_execution_enabled']) ??
              false,
      takeProfitNonActionable: _boolValue(json['take_profit_non_actionable']) ??
          _boolValue(safety['take_profit_non_actionable']) ??
          true,
      takeProfitActionable: _boolValue(json['take_profit_actionable']) ??
          _boolValue(safety['take_profit_actionable']) ??
          false,
      takeProfitReadinessOnly: _boolValue(json['take_profit_readiness_only']) ??
          _boolValue(safety['take_profit_readiness_only']) ??
          (finalCandidate?.takeProfitReadinessOnly ?? false),
      takeProfitExecutionDisabled:
          _boolValue(json['take_profit_execution_disabled']) ??
              _boolValue(safety['take_profit_execution_disabled']) ??
              (finalCandidate?.takeProfitExecutionDisabled ?? false),
      stopLossTriggered: _boolValue(json['stop_loss_triggered']) ??
          (finalCandidate?.stopLossTriggered ?? false),
      takeProfitTriggered: _boolValue(json['take_profit_triggered']) ??
          (finalCandidate?.takeProfitTriggered ?? false),
      weakTrendTriggered: _boolValue(json['weak_trend_triggered']) ??
          (finalCandidate?.weakTrendTriggered ?? false),
      sellPressureTriggered: _boolValue(json['sell_pressure_triggered']) ??
          (finalCandidate?.sellPressureTriggered ?? false),
      candidateCount:
          _nullableInt(json['candidate_count']) ?? candidates.length,
      candidates: candidates,
      finalCandidate: finalCandidate,
      checks: checks,
      safety: safety,
      dailyLimit: dailyLimit,
      duplicateOrderCheck: duplicateOrderCheck,
      auditMetadata:
          _dynamicMap(json['audit_metadata'] ?? json['source_metadata']),
      diagnostics: _dynamicMap(json['diagnostics']),
      rawPayload: _dynamicMap(json),
      createdAt: _nullableString(json['created_at'] ?? json['checked_at']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentValue: _nullableDouble(json['current_value']),
      currentPrice: _nullableDouble(json['current_price']),
      notional: _nullableDouble(json['notional']),
      stopLossThresholdPct: _nullableDouble(json['stop_loss_threshold_pct']),
      takeProfitThresholdPct:
          _nullableDouble(json['take_profit_threshold_pct']),
      dailyLimitRemaining: _nullableInt(
        json['daily_limit_remaining'] ??
            dailyLimit['daily_limit_remaining'] ??
            safety['daily_limit_remaining'],
      ),
      validationStatus: _stringValue(
        json['validation_status'],
        fallback: '',
      ),
      readinessLabels: _stringList(json['readiness_labels']),
      blockReasons: _stringList(json['block_reasons'] ?? json['blocked_by']),
      blockedBy: _stringList(json['blocked_by'] ?? json['block_reasons']),
      failedChecks: _stringList(json['failed_checks']),
    );
  }

  final String status;
  final String provider;
  final String market;
  final String mode;
  final String source;
  final String sourceType;
  final String result;
  final String action;
  final String reason;
  final String humanReadableStatus;
  final String? symbol;
  final int? quantity;
  final String? trigger;
  final String? triggerSource;
  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool autoBuyEnabled;
  final bool autoSellEnabled;
  final bool schedulerRealOrderEnabled;
  final bool liveAutoSellEnabled;
  final bool stopLossAutoSellEnabled;
  final bool takeProfitAutoSellEnabled;
  final bool schedulerRealOrdersEnabled;
  final bool dryRun;
  final bool killSwitch;
  final bool kisEnabled;
  final bool kisRealOrderEnabled;
  final bool marketOpen;
  final bool sellSessionAllowed;
  final bool autoOrderReady;
  final bool realOrderSubmitAllowed;
  final bool stopLossExecutionEnabled;
  final bool takeProfitReadinessEnabled;
  final bool takeProfitExecutionEnabled;
  final bool takeProfitNonActionable;
  final bool takeProfitActionable;
  final bool takeProfitReadinessOnly;
  final bool takeProfitExecutionDisabled;
  final bool stopLossTriggered;
  final bool takeProfitTriggered;
  final bool weakTrendTriggered;
  final bool sellPressureTriggered;
  final int candidateCount;
  final List<KisLimitedAutoSellCandidate> candidates;
  final KisLimitedAutoSellCandidate? finalCandidate;
  final Map<String, dynamic> checks;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> dailyLimit;
  final Map<String, dynamic> duplicateOrderCheck;
  final Map<String, dynamic> auditMetadata;
  final Map<String, dynamic> diagnostics;
  final Map<String, dynamic> rawPayload;
  final String? createdAt;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final double? costBasis;
  final double? currentValue;
  final double? currentPrice;
  final double? notional;
  final double? stopLossThresholdPct;
  final double? takeProfitThresholdPct;
  final String? primaryBlockReason;
  final int? dailyLimitRemaining;
  final String validationStatus;
  final List<String> readinessLabels;
  final List<String> blockReasons;
  final List<String> blockedBy;
  final List<String> failedChecks;

  bool get submitted => realOrderSubmitted || result == 'submitted';

  bool get brokerSubmitActuallyCalled =>
      realOrderSubmitted == true && brokerSubmitCalled == true;

  bool get isStatus => mode.contains('status');

  bool get isPreflight => mode.contains('preflight');

  bool check(String key) => _boolValue(checks[key]) ?? false;

  bool? nullableCheck(String key) => _boolValue(checks[key]);

  bool safetyFlag(String key) => _boolValue(safety[key]) ?? false;

  int? safetyInt(String key) => _nullableInt(safety[key]);

  double? safetyDouble(String key) => _nullableDouble(safety[key]);

  int? dailyLimitInt(String key) => _nullableInt(dailyLimit[key]);

  bool duplicateOrderFlag(String key) =>
      _boolValue(duplicateOrderCheck[key]) ?? false;
}

List<KisLimitedAutoSellCandidate> _candidateList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map)
        KisLimitedAutoSellCandidate.fromJson(
          Map<String, dynamic>.from(item),
        ),
  ];
}

KisLimitedAutoSellCandidate? _legacyCandidate(Map<String, dynamic> json) {
  final symbol = _nullableString(json['symbol']);
  if (symbol == null) return null;
  return KisLimitedAutoSellCandidate.fromJson({
    'symbol': symbol,
    'name': json['name'] ?? json['company_name'],
    'quantity': json['quantity'] ?? json['qty'],
    'current_price': json['current_price'],
    'cost_basis': json['cost_basis'],
    'current_value': json['current_value'],
    'unrealized_pl': json['unrealized_pl'],
    'unrealized_pl_pct': json['unrealized_pl_pct'],
    'stop_loss_threshold_pct': json['stop_loss_threshold_pct'],
    'take_profit_threshold_pct': json['take_profit_threshold_pct'],
    'stop_loss_triggered': json['stop_loss_triggered'] ??
        (json['trigger'] == 'stop_loss' || json['exit_trigger'] == 'stop_loss'),
    'take_profit_triggered': json['take_profit_triggered'] ??
        (json['trigger'] == 'take_profit' ||
            json['exit_trigger'] == 'take_profit'),
    'take_profit_readiness_only': json['take_profit_readiness_only'],
    'take_profit_actionable': json['take_profit_actionable'],
    'take_profit_execution_disabled': json['take_profit_execution_disabled'],
    'status': json['action'] == 'sell' ? 'SELL_READY' : 'HOLD',
    'reason': json['reason'],
    'risk_flags': json['risk_flags'],
    'gating_notes': json['gating_notes'],
    'block_reasons': json['block_reasons'] ?? json['blocked_by'],
  });
}

Map<String, dynamic> _dynamicMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
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

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim();
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
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}
