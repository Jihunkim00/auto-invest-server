class KisSchedulerDryRunOrchestration {
  const KisSchedulerDryRunOrchestration({
    required this.provider,
    required this.market,
    required this.mode,
    required this.triggerSource,
    required this.slotLabel,
    required this.result,
    required this.readinessOnly,
    required this.dryRun,
    required this.schedulerRealOrdersEnabled,
    required this.realOrderSubmitAllowed,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.summary,
    required this.childRuns,
    required this.safety,
    required this.diagnostics,
    required this.rawPayload,
    this.parentRunId,
    this.parentRunKey,
    this.blockReasons = const [],
  });

  factory KisSchedulerDryRunOrchestration.fromJson(Map<String, dynamic> json) {
    final safety = _dynamicMap(json['safety']);
    return KisSchedulerDryRunOrchestration(
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(
        json['mode'],
        fallback: 'kis_scheduler_dry_run_orchestration',
      ),
      triggerSource: _stringValue(
        json['trigger_source'],
        fallback: 'scheduler_dry_run_orchestration',
      ),
      slotLabel: _stringValue(json['slot_label'], fallback: 'manual_dry_run'),
      result: _stringValue(json['result'], fallback: 'blocked'),
      readinessOnly: _boolValue(json['readiness_only']) ?? true,
      dryRun: _boolValue(json['dry_run']) ?? true,
      schedulerRealOrdersEnabled:
          _boolValue(json['scheduler_real_orders_enabled']) ?? false,
      realOrderSubmitAllowed:
          _boolValue(json['real_order_submit_allowed']) ?? false,
      realOrderSubmitted: _boolValue(
              json['real_order_submitted'] ?? safety['real_order_submitted']) ??
          false,
      brokerSubmitCalled: _boolValue(
              json['broker_submit_called'] ?? safety['broker_submit_called']) ??
          false,
      manualSubmitCalled: _boolValue(
              json['manual_submit_called'] ?? safety['manual_submit_called']) ??
          false,
      parentRunId: _nullableString(json['parent_run_id']),
      parentRunKey: _nullableString(json['parent_run_key']),
      childRuns: _childRunList(json['child_runs']),
      summary: KisSchedulerDryRunSummary.fromJson(
        _dynamicMap(json['summary']),
      ),
      blockReasons: _stringList(json['block_reasons']),
      safety: safety,
      diagnostics: _dynamicMap(json['diagnostics']),
      rawPayload: _dynamicMap(json),
    );
  }

  final String provider;
  final String market;
  final String mode;
  final String triggerSource;
  final String slotLabel;
  final String result;
  final bool readinessOnly;
  final bool dryRun;
  final bool schedulerRealOrdersEnabled;
  final bool realOrderSubmitAllowed;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String? parentRunId;
  final String? parentRunKey;
  final List<KisSchedulerDryRunChild> childRuns;
  final KisSchedulerDryRunSummary summary;
  final List<String> blockReasons;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> diagnostics;
  final Map<String, dynamic> rawPayload;
}

class KisSchedulerDryRunSummary {
  const KisSchedulerDryRunSummary({
    required this.modulesRequested,
    required this.modulesCompleted,
    required this.modulesBlocked,
    required this.sellCandidatesReviewed,
    required this.buyCandidatesReviewed,
    required this.sellReadyCount,
    required this.buyReadyCount,
    required this.submittedOrderCount,
    required this.brokerSubmitCount,
    required this.manualSubmitCount,
    required this.realOrderSubmitAllowed,
    this.primaryBlockReason,
    this.topBlockReasons = const [],
    this.nextRecommendedOperatorAction,
  });

  factory KisSchedulerDryRunSummary.fromJson(Map<String, dynamic> json) {
    return KisSchedulerDryRunSummary(
      modulesRequested: _stringList(json['modules_requested']),
      modulesCompleted: _stringList(json['modules_completed']),
      modulesBlocked: _stringList(json['modules_blocked']),
      sellCandidatesReviewed: _intValue(json['sell_candidates_reviewed']),
      buyCandidatesReviewed: _intValue(json['buy_candidates_reviewed']),
      sellReadyCount: _intValue(json['sell_ready_count']),
      buyReadyCount: _intValue(json['buy_ready_count']),
      submittedOrderCount: _intValue(json['submitted_order_count']),
      brokerSubmitCount: _intValue(json['broker_submit_count']),
      manualSubmitCount: _intValue(json['manual_submit_count']),
      realOrderSubmitAllowed:
          _boolValue(json['real_order_submit_allowed']) ?? false,
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      topBlockReasons: _stringList(json['top_block_reasons']),
      nextRecommendedOperatorAction:
          _nullableString(json['next_recommended_operator_action']),
    );
  }

  final List<String> modulesRequested;
  final List<String> modulesCompleted;
  final List<String> modulesBlocked;
  final int sellCandidatesReviewed;
  final int buyCandidatesReviewed;
  final int sellReadyCount;
  final int buyReadyCount;
  final int submittedOrderCount;
  final int brokerSubmitCount;
  final int manualSubmitCount;
  final bool realOrderSubmitAllowed;
  final String? primaryBlockReason;
  final List<String> topBlockReasons;
  final String? nextRecommendedOperatorAction;
}

class KisSchedulerDryRunChild {
  const KisSchedulerDryRunChild({
    required this.module,
    required this.result,
    required this.action,
    required this.status,
    required this.blockReasons,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.source,
    required this.mode,
    required this.triggerSource,
    required this.summary,
    required this.rawPayload,
    this.symbol,
    this.primaryBlockReason,
    this.orderId,
  });

  factory KisSchedulerDryRunChild.fromJson(Map<String, dynamic> json) {
    return KisSchedulerDryRunChild(
      module: _stringValue(json['module'], fallback: 'module'),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      symbol: _nullableString(json['symbol']),
      status: _stringValue(json['status'], fallback: 'n/a'),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      blockReasons: _stringList(json['block_reasons']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      orderId: _nullableString(json['order_id']),
      source: _stringValue(json['source'], fallback: ''),
      mode: _stringValue(json['mode'], fallback: ''),
      triggerSource: _stringValue(json['trigger_source'], fallback: ''),
      summary: _dynamicMap(json['summary']),
      rawPayload: _dynamicMap(json['raw_payload']),
    );
  }

  final String module;
  final String result;
  final String action;
  final String? symbol;
  final String status;
  final String? primaryBlockReason;
  final List<String> blockReasons;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String? orderId;
  final String source;
  final String mode;
  final String triggerSource;
  final Map<String, dynamic> summary;
  final Map<String, dynamic> rawPayload;
}

List<KisSchedulerDryRunChild> _childRunList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) =>
          KisSchedulerDryRunChild.fromJson(Map<String, dynamic>.from(item)))
      .toList();
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

bool? _boolValue(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

int _intValue(Object? value) {
  if (value is num) return value.toInt();
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return 0;
  return int.tryParse(text) ?? 0;
}

List<String> _stringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}
