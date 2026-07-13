class AutomationReleaseChecklistItem {
  const AutomationReleaseChecklistItem({
    required this.key,
    required this.label,
    required this.passed,
    required this.severity,
    required this.blocking,
    required this.nextAction,
    this.reason,
  });

  final String key;
  final String label;
  final bool passed;
  final String severity;
  final String? reason;
  final bool blocking;
  final String nextAction;

  bool get failed => !passed;

  factory AutomationReleaseChecklistItem.fromJson(Object? value) {
    if (value is! Map) {
      return const AutomationReleaseChecklistItem(
        key: 'unknown',
        label: 'Unknown',
        passed: false,
        severity: 'warning',
        blocking: false,
        nextAction: 'manual_review',
      );
    }
    final json = Map<String, dynamic>.from(value);
    return AutomationReleaseChecklistItem(
      key: _string(json['key'], 'unknown'),
      label: _string(json['label'], 'Unknown'),
      passed: _bool(json['passed']) ?? false,
      severity: _string(json['severity'], 'warning'),
      reason: _nullableString(json['reason']),
      blocking: _bool(json['blocking']) ?? false,
      nextAction: _string(json['next_action'], 'manual_review'),
    );
  }
}

class AutomationReleaseStatus {
  const AutomationReleaseStatus({
    required this.generatedAt,
    required this.releaseEnabled,
    required this.releaseMode,
    required this.releaseArmed,
    required this.effectiveStatus,
    required this.canRunMonitoringCycle,
    required this.canRunDryRunCycle,
    required this.canRunLivePhase1Cycle,
    required this.canSubmitLiveOrder,
    required this.automationModeStatus,
    required this.brokerSyncStatus,
    required this.soakStatus,
    required this.killLatchActive,
    required this.productionReadinessStatus,
    required this.orchestratorStatus,
    required this.autoBuyPhase1Status,
    required this.autoSellPhase1Status,
    required this.dailyTradeLimitRemaining,
    required this.dailyAutoBuyRemaining,
    required this.dailyAutoSellRemaining,
    required this.blockingReasons,
    required this.warningReasons,
    required this.checklist,
    required this.safetyFlags,
    required this.nextSafeAction,
    this.releaseArmedAt,
    this.releaseReason,
  });

  final DateTime generatedAt;
  final bool releaseEnabled;
  final String releaseMode;
  final bool releaseArmed;
  final DateTime? releaseArmedAt;
  final String? releaseReason;
  final String effectiveStatus;
  final bool canRunMonitoringCycle;
  final bool canRunDryRunCycle;
  final bool canRunLivePhase1Cycle;
  final bool canSubmitLiveOrder;
  final Map<String, dynamic> automationModeStatus;
  final Map<String, dynamic> brokerSyncStatus;
  final Map<String, dynamic> soakStatus;
  final bool killLatchActive;
  final String productionReadinessStatus;
  final Map<String, dynamic> orchestratorStatus;
  final Map<String, dynamic> autoBuyPhase1Status;
  final Map<String, dynamic> autoSellPhase1Status;
  final int dailyTradeLimitRemaining;
  final int dailyAutoBuyRemaining;
  final int dailyAutoSellRemaining;
  final List<String> blockingReasons;
  final List<String> warningReasons;
  final List<AutomationReleaseChecklistItem> checklist;
  final Map<String, dynamic> safetyFlags;
  final String nextSafeAction;

  bool get liveReady => effectiveStatus == 'live_ready';
  bool get disabled => effectiveStatus == 'disabled';

  factory AutomationReleaseStatus.fromJson(Map<String, dynamic> json) {
    return AutomationReleaseStatus(
      generatedAt: _dateTime(json['generated_at']) ?? DateTime.now(),
      releaseEnabled: _bool(json['release_enabled']) ?? false,
      releaseMode: _string(json['release_mode'], 'controlled_phase1'),
      releaseArmed: _bool(json['release_armed']) ?? false,
      releaseArmedAt: _dateTime(json['release_armed_at']),
      releaseReason: _nullableString(json['release_reason']),
      effectiveStatus: _string(json['effective_status'], 'disabled'),
      canRunMonitoringCycle: _bool(json['can_run_monitoring_cycle']) ?? false,
      canRunDryRunCycle: _bool(json['can_run_dry_run_cycle']) ?? false,
      canRunLivePhase1Cycle: _bool(json['can_run_live_phase1_cycle']) ?? false,
      canSubmitLiveOrder: _bool(json['can_submit_live_order']) ?? false,
      automationModeStatus: _map(json['automation_mode_status']),
      brokerSyncStatus: _map(json['broker_sync_status']),
      soakStatus: _map(json['soak_status']),
      killLatchActive: _bool(json['kill_latch_active']) ?? false,
      productionReadinessStatus:
          _string(json['production_readiness_status'], 'unknown'),
      orchestratorStatus: _map(json['orchestrator_status']),
      autoBuyPhase1Status: _map(json['auto_buy_phase1_status']),
      autoSellPhase1Status: _map(json['auto_sell_phase1_status']),
      dailyTradeLimitRemaining: _int(json['daily_trade_limit_remaining']),
      dailyAutoBuyRemaining: _int(json['daily_auto_buy_remaining']),
      dailyAutoSellRemaining: _int(json['daily_auto_sell_remaining']),
      blockingReasons: _strings(json['blocking_reasons']),
      warningReasons: _strings(json['warning_reasons']),
      checklist: _checklist(json['checklist']),
      safetyFlags: _map(json['safety_flags']),
      nextSafeAction: _string(json['next_safe_action'], 'manual_review'),
    );
  }
}

class AutomationReleaseCycleResult {
  const AutomationReleaseCycleResult({
    required this.generatedAt,
    required this.releaseEnabled,
    required this.releaseMode,
    required this.cycleMode,
    required this.resultStatus,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.orderCancelCalled,
    required this.actionTaken,
    required this.checklist,
    required this.blockingReasons,
    required this.warningReasons,
    required this.riskFlags,
    required this.gatingNotes,
    required this.nextSafeAction,
    required this.safetyFlags,
    this.runId,
    this.orchestratorRunId,
    this.soakRunId,
  });

  final int? runId;
  final DateTime generatedAt;
  final bool releaseEnabled;
  final String releaseMode;
  final String cycleMode;
  final String resultStatus;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool orderCancelCalled;
  final String actionTaken;
  final int? orchestratorRunId;
  final int? soakRunId;
  final List<AutomationReleaseChecklistItem> checklist;
  final List<String> blockingReasons;
  final List<String> warningReasons;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final String nextSafeAction;
  final Map<String, dynamic> safetyFlags;

  bool get completed => {
        'monitoring_completed',
        'dry_run_completed',
        'live_phase1_completed',
        'live_order_submitted',
        'no_action',
      }.contains(resultStatus);

  factory AutomationReleaseCycleResult.fromJson(Map<String, dynamic> json) {
    return AutomationReleaseCycleResult(
      runId: _nullableInt(json['run_id']),
      generatedAt: _dateTime(json['generated_at']) ?? DateTime.now(),
      releaseEnabled: _bool(json['release_enabled']) ?? false,
      releaseMode: _string(json['release_mode'], 'controlled_phase1'),
      cycleMode: _string(json['cycle_mode'], 'monitoring'),
      resultStatus: _string(json['result_status'], 'blocked'),
      realOrderSubmitted: _bool(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _bool(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _bool(json['manual_submit_called']) ?? false,
      orderCancelCalled: _bool(json['order_cancel_called']) ?? false,
      actionTaken: _string(json['action_taken'], 'none'),
      orchestratorRunId: _nullableInt(json['orchestrator_run_id']),
      soakRunId: _nullableInt(json['soak_run_id']),
      checklist: _checklist(json['checklist']),
      blockingReasons: _strings(json['blocking_reasons']),
      warningReasons: _strings(json['warning_reasons']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      nextSafeAction: _string(json['next_safe_action'], 'manual_review'),
      safetyFlags: _map(json['safety_flags']),
    );
  }
}

int _int(Object? value, {int fallback = 0}) => _nullableInt(value) ?? fallback;

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString().trim());
}

String _string(Object? value, String fallback) =>
    _nullableString(value) ?? fallback;

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
      ? Map<String, dynamic>.unmodifiable(Map<String, dynamic>.from(value))
      : const <String, dynamic>{};
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return List<String>.unmodifiable([
    for (final item in value)
      if (item.toString().trim().isNotEmpty) item.toString().trim(),
  ]);
}

List<AutomationReleaseChecklistItem> _checklist(Object? value) {
  if (value is! List) return const [];
  return List<AutomationReleaseChecklistItem>.unmodifiable([
    for (final item in value) AutomationReleaseChecklistItem.fromJson(item),
  ]);
}
