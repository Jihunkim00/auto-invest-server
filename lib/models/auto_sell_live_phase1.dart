class AutoSellLivePhase1ChecklistItem {
  const AutoSellLivePhase1ChecklistItem({
    required this.key,
    required this.status,
    required this.ok,
    required this.blocking,
    this.reason,
    this.detail,
  });

  final String key;
  final String status;
  final bool ok;
  final bool blocking;
  final String? reason;
  final String? detail;

  bool get failed => !ok || status == 'fail' || blocking;

  factory AutoSellLivePhase1ChecklistItem.fromJson(Object? value) {
    if (value is! Map) {
      return const AutoSellLivePhase1ChecklistItem(
        key: 'check',
        status: 'pass',
        ok: true,
        blocking: false,
      );
    }
    final json = Map<String, dynamic>.from(value);
    final ok = _bool(json['ok']) ?? json['status'] == 'pass';
    return AutoSellLivePhase1ChecklistItem(
      key: _string(json['key'], 'check'),
      status: _string(json['status'], ok ? 'pass' : 'fail'),
      ok: ok,
      blocking: _bool(json['blocking']) ?? !ok,
      reason: _nullableString(json['reason']),
      detail: _nullableString(json['detail']),
    );
  }
}

class AutoSellLivePhase1LatestRun {
  const AutoSellLivePhase1LatestRun({
    this.runId,
    this.generatedAt,
    this.triggerSource,
    this.resultStatus,
    this.selectedCandidateId,
    this.selectedSymbol,
    this.candidateType,
    this.candidateSeverity,
    this.primaryBlockReason,
    this.realOrderSubmitted = false,
    this.brokerSubmitCalled = false,
    this.orderId,
    this.brokerOrderId,
  });

  final int? runId;
  final DateTime? generatedAt;
  final String? triggerSource;
  final String? resultStatus;
  final String? selectedCandidateId;
  final String? selectedSymbol;
  final String? candidateType;
  final String? candidateSeverity;
  final String? primaryBlockReason;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final int? orderId;
  final String? brokerOrderId;

  factory AutoSellLivePhase1LatestRun.fromJson(Object? value) {
    if (value is! Map) return const AutoSellLivePhase1LatestRun();
    final json = Map<String, dynamic>.from(value);
    return AutoSellLivePhase1LatestRun(
      runId: _nullableInt(json['run_id']),
      generatedAt: _dateTime(json['generated_at']),
      triggerSource: _nullableString(json['trigger_source']),
      resultStatus: _nullableString(json['result_status']),
      selectedCandidateId: _nullableString(json['selected_candidate_id']),
      selectedSymbol: _nullableString(json['selected_symbol']),
      candidateType: _nullableString(json['candidate_type']),
      candidateSeverity: _nullableString(json['candidate_severity']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      realOrderSubmitted: _bool(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _bool(json['broker_submit_called']) ?? false,
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
    );
  }
}

class AutoSellLivePhase1Result {
  const AutoSellLivePhase1Result({
    required this.generatedAt,
    required this.provider,
    required this.market,
    required this.triggerSource,
    required this.automationPhase,
    required this.autoSellLiveEnabled,
    required this.resultStatus,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.dailyAutoSellCount,
    required this.dailyAutoSellLimit,
    required this.riskFlags,
    required this.gatingNotes,
    required this.checklist,
    required this.nextSafeAction,
    required this.safety,
    this.runId,
    this.selectedCandidateId,
    this.selectedSymbol,
    this.candidateType,
    this.candidateSeverity,
    this.productionReadinessStatus,
    this.sellPreflightStatus,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    this.submittedQuantity,
    this.submittedNotional,
    this.availableQuantity,
    this.primaryBlockReason,
    this.latestRun,
  });

  final int? runId;
  final DateTime generatedAt;
  final String provider;
  final String market;
  final String triggerSource;
  final String automationPhase;
  final bool autoSellLiveEnabled;
  final String resultStatus;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String? selectedCandidateId;
  final String? selectedSymbol;
  final String? candidateType;
  final String? candidateSeverity;
  final String? productionReadinessStatus;
  final String? sellPreflightStatus;
  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final double? submittedQuantity;
  final double? submittedNotional;
  final double? availableQuantity;
  final int dailyAutoSellCount;
  final int dailyAutoSellLimit;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<AutoSellLivePhase1ChecklistItem> checklist;
  final String? primaryBlockReason;
  final String nextSafeAction;
  final AutoSellLivePhase1LatestRun? latestRun;
  final Map<String, dynamic> safety;

  bool get blocked =>
      resultStatus == 'blocked' ||
      resultStatus == 'disabled' ||
      resultStatus == 'dry_run_blocked' ||
      resultStatus == 'rejected' ||
      resultStatus == 'error';

  bool get submitted =>
      resultStatus == 'submitted' ||
      resultStatus == 'filled' ||
      resultStatus == 'pending_sync';

  int get dailyRemaining => (dailyAutoSellLimit - dailyAutoSellCount)
      .clamp(0, dailyAutoSellLimit)
      .toInt();

  factory AutoSellLivePhase1Result.fromJson(Map<String, dynamic> json) {
    return AutoSellLivePhase1Result(
      runId: _nullableInt(json['run_id']),
      generatedAt: _dateTime(json['generated_at']) ?? DateTime.now(),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      triggerSource: _string(json['trigger_source'], 'manual_phase1_test'),
      automationPhase: _string(json['automation_phase'], 'phase1_auto_sell'),
      autoSellLiveEnabled: _bool(json['auto_sell_live_enabled']) ?? false,
      resultStatus: _string(json['result_status'], 'skipped'),
      realOrderSubmitted: _bool(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _bool(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _bool(json['manual_submit_called']) ?? false,
      selectedCandidateId: _nullableString(json['selected_candidate_id']),
      selectedSymbol: _nullableString(json['selected_symbol']),
      candidateType: _nullableString(json['candidate_type']),
      candidateSeverity: _nullableString(json['candidate_severity']),
      productionReadinessStatus:
          _nullableString(json['production_readiness_status']),
      sellPreflightStatus: _nullableString(json['sell_preflight_status']),
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      submittedQuantity: _nullableDouble(json['submitted_quantity']),
      submittedNotional: _nullableDouble(json['submitted_notional']),
      availableQuantity: _nullableDouble(json['available_quantity']),
      dailyAutoSellCount: _int(json['daily_auto_sell_count']),
      dailyAutoSellLimit: _int(json['daily_auto_sell_limit'], fallback: 1),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      checklist: _checklist(json['checklist']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      nextSafeAction: _string(json['next_safe_action'], 'review_result'),
      latestRun: json['latest_run'] == null
          ? null
          : AutoSellLivePhase1LatestRun.fromJson(json['latest_run']),
      safety: _map(json['safety']),
    );
  }
}

int _int(Object? value, {int fallback = 0}) => _nullableInt(value) ?? fallback;

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString().trim());
}

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString().replaceAll(',', '').trim());
}

String _string(Object? value, String fallback) {
  final text = _nullableString(value);
  return text ?? fallback;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

bool? _bool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

DateTime? _dateTime(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return DateTime.tryParse(text);
}

Map<String, dynamic> _map(Object? value) {
  return value is Map
      ? Map<String, dynamic>.from(value)
      : const <String, dynamic>{};
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item.toString().trim().isNotEmpty) item.toString(),
  ];
}

List<AutoSellLivePhase1ChecklistItem> _checklist(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value) AutoSellLivePhase1ChecklistItem.fromJson(item),
  ];
}
