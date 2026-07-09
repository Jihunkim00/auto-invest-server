class AutoBuyLivePhase1ChecklistItem {
  const AutoBuyLivePhase1ChecklistItem({
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

  factory AutoBuyLivePhase1ChecklistItem.fromJson(Object? value) {
    if (value is! Map) {
      return const AutoBuyLivePhase1ChecklistItem(
        key: 'check',
        status: 'pass',
        ok: true,
        blocking: false,
      );
    }
    final json = Map<String, dynamic>.from(value);
    final ok = _bool(json['ok']) ?? json['status'] == 'pass';
    return AutoBuyLivePhase1ChecklistItem(
      key: _string(json['key'], 'check'),
      status: _string(json['status'], ok ? 'pass' : 'fail'),
      ok: ok,
      blocking: _bool(json['blocking']) ?? !ok,
      reason: _nullableString(json['reason']),
      detail: _nullableString(json['detail']),
    );
  }
}

class AutoBuyLivePhase1LatestRun {
  const AutoBuyLivePhase1LatestRun({
    this.runId,
    this.generatedAt,
    this.triggerSource,
    this.resultStatus,
    this.selectedPromotionId,
    this.selectedSymbol,
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
  final int? selectedPromotionId;
  final String? selectedSymbol;
  final String? primaryBlockReason;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final int? orderId;
  final String? brokerOrderId;

  factory AutoBuyLivePhase1LatestRun.fromJson(Object? value) {
    if (value is! Map) return const AutoBuyLivePhase1LatestRun();
    final json = Map<String, dynamic>.from(value);
    return AutoBuyLivePhase1LatestRun(
      runId: _nullableInt(json['run_id']),
      generatedAt: _dateTime(json['generated_at']),
      triggerSource: _nullableString(json['trigger_source']),
      resultStatus: _nullableString(json['result_status']),
      selectedPromotionId: _nullableInt(json['selected_promotion_id']),
      selectedSymbol: _nullableString(json['selected_symbol']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      realOrderSubmitted: _bool(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _bool(json['broker_submit_called']) ?? false,
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
    );
  }
}

class AutoBuyLivePhase1Result {
  const AutoBuyLivePhase1Result({
    required this.generatedAt,
    required this.provider,
    required this.market,
    required this.triggerSource,
    required this.automationPhase,
    required this.autoBuyLiveEnabled,
    required this.resultStatus,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.dailyAutoBuyCount,
    required this.dailyAutoBuyLimit,
    required this.riskFlags,
    required this.gatingNotes,
    required this.checklist,
    required this.nextSafeAction,
    required this.safety,
    this.runId,
    this.selectedPromotionId,
    this.selectedSymbol,
    this.candidateScore,
    this.productionReadinessStatus,
    this.preflightStatus,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    this.submittedQuantity,
    this.submittedNotional,
    this.maxAllowedNotional,
    this.primaryBlockReason,
    this.latestRun,
  });

  final int? runId;
  final DateTime generatedAt;
  final String provider;
  final String market;
  final String triggerSource;
  final String automationPhase;
  final bool autoBuyLiveEnabled;
  final String resultStatus;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final int? selectedPromotionId;
  final String? selectedSymbol;
  final double? candidateScore;
  final String? productionReadinessStatus;
  final String? preflightStatus;
  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final double? submittedQuantity;
  final double? submittedNotional;
  final double? maxAllowedNotional;
  final int dailyAutoBuyCount;
  final int dailyAutoBuyLimit;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<AutoBuyLivePhase1ChecklistItem> checklist;
  final String? primaryBlockReason;
  final String nextSafeAction;
  final AutoBuyLivePhase1LatestRun? latestRun;
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

  int get dailyRemaining => (dailyAutoBuyLimit - dailyAutoBuyCount)
      .clamp(0, dailyAutoBuyLimit)
      .toInt();

  factory AutoBuyLivePhase1Result.fromJson(Map<String, dynamic> json) {
    return AutoBuyLivePhase1Result(
      runId: _nullableInt(json['run_id']),
      generatedAt: _dateTime(json['generated_at']) ?? DateTime.now(),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      triggerSource: _string(json['trigger_source'], 'manual_phase1_test'),
      automationPhase: _string(json['automation_phase'], 'phase1_auto_buy'),
      autoBuyLiveEnabled: _bool(json['auto_buy_live_enabled']) ?? false,
      resultStatus: _string(json['result_status'], 'skipped'),
      realOrderSubmitted: _bool(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _bool(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _bool(json['manual_submit_called']) ?? false,
      selectedPromotionId: _nullableInt(json['selected_promotion_id']),
      selectedSymbol: _nullableString(json['selected_symbol']),
      candidateScore: _nullableDouble(json['candidate_score']),
      productionReadinessStatus:
          _nullableString(json['production_readiness_status']),
      preflightStatus: _nullableString(json['preflight_status']),
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      submittedQuantity: _nullableDouble(json['submitted_quantity']),
      submittedNotional: _nullableDouble(json['submitted_notional']),
      maxAllowedNotional: _nullableDouble(json['max_allowed_notional']),
      dailyAutoBuyCount: _int(json['daily_auto_buy_count']),
      dailyAutoBuyLimit: _int(json['daily_auto_buy_limit'], fallback: 1),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      checklist: _checklist(json['checklist']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      nextSafeAction: _string(json['next_safe_action'], 'review_result'),
      latestRun: json['latest_run'] == null
          ? null
          : AutoBuyLivePhase1LatestRun.fromJson(json['latest_run']),
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

List<AutoBuyLivePhase1ChecklistItem> _checklist(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value) AutoBuyLivePhase1ChecklistItem.fromJson(item),
  ];
}
