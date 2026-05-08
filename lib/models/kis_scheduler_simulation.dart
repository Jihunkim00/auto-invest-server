class KisSchedulerSimulationStatus {
  const KisSchedulerSimulationStatus({
    required this.provider,
    required this.market,
    required this.enabled,
    required this.dryRun,
    required this.allowRealOrders,
    required this.realOrdersAllowed,
    required this.realOrderSchedulerEnabled,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.schedulerDryRun,
    this.configuredAllowRealOrders,
    this.runtimeSchedulerEnabled,
    this.runtimeDryRun,
    this.killSwitch,
  });

  factory KisSchedulerSimulationStatus.fromJson(Map<String, dynamic> json) {
    final safety = _optionalMap(json['safety']);
    return KisSchedulerSimulationStatus(
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      enabled:
          _boolValue(json['enabled'] ?? json['kis_scheduler_enabled']) ?? false,
      dryRun:
          _boolValue(json['dry_run'] ?? json['kis_scheduler_dry_run']) ?? true,
      schedulerDryRun: _boolValue(
          json['scheduler_dry_run'] ?? json['kis_scheduler_dry_run']),
      allowRealOrders: _boolValue(json['allow_real_orders'] ??
              json['kis_scheduler_allow_real_orders']) ??
          false,
      configuredAllowRealOrders: _boolValue(
          json['configured_allow_real_orders'] ??
              json['kis_scheduler_allow_real_orders']),
      realOrdersAllowed: _boolValue(json['real_orders_allowed']) ?? false,
      realOrderSchedulerEnabled: _boolValue(
            json['real_order_scheduler_enabled'] ??
                json['live_scheduler_orders_enabled'] ??
                safety?['live_scheduler_orders_enabled'],
          ) ??
          false,
      runtimeSchedulerEnabled: _boolValue(json['runtime_scheduler_enabled']),
      runtimeDryRun: _boolValue(json['runtime_dry_run']),
      killSwitch: _boolValue(json['kill_switch']),
      realOrderSubmitted: _boolValue(json['real_order_submitted'] ??
              safety?['real_order_submitted']) ??
          false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called'] ??
              safety?['broker_submit_called']) ??
          false,
      manualSubmitCalled: _boolValue(json['manual_submit_called'] ??
              safety?['manual_submit_called']) ??
          false,
    );
  }

  factory KisSchedulerSimulationStatus.safeDefault() {
    return const KisSchedulerSimulationStatus(
      provider: 'kis',
      market: 'KR',
      enabled: false,
      dryRun: true,
      schedulerDryRun: true,
      allowRealOrders: false,
      configuredAllowRealOrders: false,
      realOrdersAllowed: false,
      realOrderSchedulerEnabled: false,
      runtimeSchedulerEnabled: false,
      runtimeDryRun: true,
      killSwitch: false,
      realOrderSubmitted: false,
      brokerSubmitCalled: false,
      manualSubmitCalled: false,
    );
  }

  final String provider;
  final String market;
  final bool enabled;
  final bool dryRun;
  final bool? schedulerDryRun;
  final bool allowRealOrders;
  final bool? configuredAllowRealOrders;
  final bool realOrdersAllowed;
  final bool realOrderSchedulerEnabled;
  final bool? runtimeSchedulerEnabled;
  final bool? runtimeDryRun;
  final bool? killSwitch;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
}

class KisSchedulerRunResult {
  const KisSchedulerRunResult({
    required this.provider,
    required this.market,
    required this.mode,
    required this.dryRun,
    required this.simulated,
    required this.schedulerDryRun,
    required this.schedulerAllowRealOrders,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.triggerSource,
    required this.result,
    required this.action,
    required this.reason,
    this.schedulerEnabled,
    this.configuredAllowRealOrders,
    this.schedulerSlot,
    this.triggeredSymbol,
    this.signalId,
    this.orderId,
    this.triggerBlockReason,
    this.quantBuyScore,
    this.quantSellScore,
    this.aiBuyScore,
    this.aiSellScore,
    this.confidence,
    this.finalEntryScore,
    this.finalScoreGap,
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.triggerSources = const [],
  });

  factory KisSchedulerRunResult.fromJson(Map<String, dynamic> json) {
    return KisSchedulerRunResult(
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(json['mode'], fallback: 'kis_scheduler_dry_run_auto'),
      dryRun: _boolValue(json['dry_run']) ?? true,
      simulated: _boolValue(json['simulated']) ?? true,
      schedulerEnabled: _boolValue(json['scheduler_enabled']),
      schedulerDryRun: _boolValue(json['scheduler_dry_run']) ?? true,
      schedulerAllowRealOrders:
          _boolValue(json['scheduler_allow_real_orders']) ?? false,
      configuredAllowRealOrders:
          _boolValue(json['configured_allow_real_orders']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      schedulerSlot: _nullableString(json['scheduler_slot']),
      triggerSource: _stringValue(
        json['trigger_source'],
        fallback: 'scheduler_kis_dry_run_auto',
      ),
      result: _stringValue(json['result'], fallback: ''),
      action: _stringValue(json['action'], fallback: 'hold'),
      triggeredSymbol: _nullableString(json['triggered_symbol']),
      signalId: _nullableInt(json['signal_id']),
      orderId: _nullableInt(json['order_id']),
      reason: _stringValue(json['reason'], fallback: ''),
      triggerBlockReason: _nullableString(json['trigger_block_reason']),
      quantBuyScore: _nullableDouble(json['quant_buy_score']),
      quantSellScore: _nullableDouble(json['quant_sell_score']),
      aiBuyScore: _nullableDouble(json['ai_buy_score']),
      aiSellScore: _nullableDouble(json['ai_sell_score']),
      confidence: _nullableDouble(json['confidence']),
      finalEntryScore: _nullableDouble(json['final_entry_score']),
      finalScoreGap: _nullableDouble(json['final_score_gap']),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      triggerSources: _stringList(json['trigger_sources']),
    );
  }

  final String provider;
  final String market;
  final String mode;
  final bool dryRun;
  final bool simulated;
  final bool? schedulerEnabled;
  final bool schedulerDryRun;
  final bool schedulerAllowRealOrders;
  final bool? configuredAllowRealOrders;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String? schedulerSlot;
  final String triggerSource;
  final String result;
  final String action;
  final String? triggeredSymbol;
  final int? signalId;
  final int? orderId;
  final String reason;
  final String? triggerBlockReason;
  final double? quantBuyScore;
  final double? quantSellScore;
  final double? aiBuyScore;
  final double? aiSellScore;
  final double? confidence;
  final double? finalEntryScore;
  final double? finalScoreGap;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<String> triggerSources;
}

Map<String, dynamic>? _optionalMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return null;
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

List<String> _stringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}
