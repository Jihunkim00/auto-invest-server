class AutomationKillRule {
  const AutomationKillRule({
    required this.ruleId,
    required this.name,
    required this.severity,
    required this.triggered,
    required this.automationBlocking,
    required this.reason,
    required this.detectedAt,
    required this.source,
    required this.recommendedAction,
  });

  final String ruleId;
  final String name;
  final String severity;
  final bool triggered;
  final bool automationBlocking;
  final String reason;
  final DateTime detectedAt;
  final String source;
  final String recommendedAction;

  bool get critical => severity == 'critical';
  bool get warning => severity == 'warning';

  factory AutomationKillRule.fromJson(Object? value) {
    if (value is! Map) {
      return AutomationKillRule(
        ruleId: 'unknown',
        name: 'Unknown',
        severity: 'info',
        triggered: false,
        automationBlocking: false,
        reason: 'unknown',
        detectedAt: DateTime.now(),
        source: 'unknown',
        recommendedAction: 'manual_review',
      );
    }
    final json = Map<String, dynamic>.from(value);
    return AutomationKillRule(
      ruleId: _string(json['rule_id'], 'unknown'),
      name: _string(json['name'], 'Unknown'),
      severity: _string(json['severity'], 'info'),
      triggered: _bool(json['triggered']) ?? false,
      automationBlocking: _bool(json['automation_blocking']) ?? false,
      reason: _string(json['reason'], 'unknown'),
      detectedAt: _dateTime(json['detected_at']) ?? DateTime.now(),
      source: _string(json['source'], 'unknown'),
      recommendedAction: _string(json['recommended_action'], 'manual_review'),
    );
  }
}

class AutomationSoakStatus {
  const AutomationSoakStatus({
    required this.generatedAt,
    required this.soakEnabled,
    required this.soakMode,
    required this.allowLivePhase1,
    required this.killLatchActive,
    required this.effectiveStatus,
    required this.canRunSoakCycle,
    required this.canAttemptLivePhase1,
    required this.canSubmitLiveOrder,
    required this.cycleCountToday,
    required this.maxCyclesPerDay,
    required this.actionCountToday,
    required this.maxActionsPerDay,
    required this.consecutiveFailureCount,
    required this.maxConsecutiveFailures,
    required this.latestOrchestratorResult,
    required this.latestWatchdogStatus,
    required this.automationModeStatus,
    required this.productionReadinessStatus,
    required this.dailyLossStatus,
    required this.killRules,
    required this.blockingReasons,
    required this.warningReasons,
    required this.nextSafeAction,
    required this.safetyFlags,
    this.killLatchReason,
    this.killLatchTriggeredAt,
  });

  final DateTime generatedAt;
  final bool soakEnabled;
  final String soakMode;
  final bool allowLivePhase1;
  final bool killLatchActive;
  final String? killLatchReason;
  final DateTime? killLatchTriggeredAt;
  final String effectiveStatus;
  final bool canRunSoakCycle;
  final bool canAttemptLivePhase1;
  final bool canSubmitLiveOrder;
  final int cycleCountToday;
  final int maxCyclesPerDay;
  final int actionCountToday;
  final int maxActionsPerDay;
  final int consecutiveFailureCount;
  final int maxConsecutiveFailures;
  final Map<String, dynamic> latestOrchestratorResult;
  final Map<String, dynamic> latestWatchdogStatus;
  final Map<String, dynamic> automationModeStatus;
  final String productionReadinessStatus;
  final String dailyLossStatus;
  final List<AutomationKillRule> killRules;
  final List<String> blockingReasons;
  final List<String> warningReasons;
  final String nextSafeAction;
  final Map<String, dynamic> safetyFlags;

  List<AutomationKillRule> get triggeredRules =>
      killRules.where((rule) => rule.triggered).toList(growable: false);

  factory AutomationSoakStatus.fromJson(Map<String, dynamic> json) {
    return AutomationSoakStatus(
      generatedAt: _dateTime(json['generated_at']) ?? DateTime.now(),
      soakEnabled: _bool(json['soak_enabled']) ?? false,
      soakMode: _string(json['soak_mode'], 'dry_run_monitoring'),
      allowLivePhase1: _bool(json['allow_live_phase1']) ?? false,
      killLatchActive: _bool(json['kill_latch_active']) ?? false,
      killLatchReason: _nullableString(json['kill_latch_reason']),
      killLatchTriggeredAt: _dateTime(json['kill_latch_triggered_at']),
      effectiveStatus: _string(json['effective_status'], 'disabled'),
      canRunSoakCycle: _bool(json['can_run_soak_cycle']) ?? false,
      canAttemptLivePhase1: _bool(json['can_attempt_live_phase1']) ?? false,
      canSubmitLiveOrder: _bool(json['can_submit_live_order']) ?? false,
      cycleCountToday: _int(json['cycle_count_today']),
      maxCyclesPerDay: _int(json['max_cycles_per_day'], fallback: 3),
      actionCountToday: _int(json['action_count_today']),
      maxActionsPerDay: _int(json['max_actions_per_day'], fallback: 1),
      consecutiveFailureCount: _int(json['consecutive_failure_count']),
      maxConsecutiveFailures:
          _int(json['max_consecutive_failures'], fallback: 2),
      latestOrchestratorResult: _map(json['latest_orchestrator_result']),
      latestWatchdogStatus: _map(json['latest_watchdog_status']),
      automationModeStatus: _map(json['automation_mode_status']),
      productionReadinessStatus:
          _string(json['production_readiness_status'], 'unknown'),
      dailyLossStatus: _string(json['daily_loss_status'], 'unknown'),
      killRules: _rules(json['kill_rules']),
      blockingReasons: _strings(json['blocking_reasons']),
      warningReasons: _strings(json['warning_reasons']),
      nextSafeAction: _string(json['next_safe_action'], 'manual_review'),
      safetyFlags: _map(json['safety_flags']),
    );
  }
}

class AutomationSoakRunResult {
  const AutomationSoakRunResult({
    required this.generatedAt,
    required this.provider,
    required this.market,
    required this.soakMode,
    required this.triggerSource,
    required this.resultStatus,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.orderCancelCalled,
    required this.actionTaken,
    required this.brokerSyncHealth,
    required this.automationModeEffectiveStatus,
    required this.productionReadinessStatus,
    required this.killRulesEvaluated,
    required this.killRulesTriggered,
    required this.killLatchActive,
    required this.cycleCountToday,
    required this.actionCountToday,
    required this.consecutiveFailureCount,
    required this.riskFlags,
    required this.gatingNotes,
    required this.blockingReasons,
    required this.warningReasons,
    required this.nextSafeAction,
    required this.safetyFlags,
    this.runId,
    this.orchestratorRunId,
  });

  final int? runId;
  final DateTime generatedAt;
  final String provider;
  final String market;
  final String soakMode;
  final String triggerSource;
  final String resultStatus;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool orderCancelCalled;
  final String actionTaken;
  final int? orchestratorRunId;
  final String brokerSyncHealth;
  final String automationModeEffectiveStatus;
  final String productionReadinessStatus;
  final List<AutomationKillRule> killRulesEvaluated;
  final List<AutomationKillRule> killRulesTriggered;
  final bool killLatchActive;
  final int cycleCountToday;
  final int actionCountToday;
  final int consecutiveFailureCount;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<String> blockingReasons;
  final List<String> warningReasons;
  final String nextSafeAction;
  final Map<String, dynamic> safetyFlags;

  bool get completed => {
        'dry_run_completed',
        'live_phase1_completed',
        'orchestrator_action_taken',
      }.contains(resultStatus);

  factory AutomationSoakRunResult.fromJson(Map<String, dynamic> json) {
    return AutomationSoakRunResult(
      runId: _nullableInt(json['run_id']),
      generatedAt: _dateTime(json['generated_at']) ?? DateTime.now(),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      soakMode: _string(json['soak_mode'], 'dry_run_monitoring'),
      triggerSource: _string(json['trigger_source'], 'manual_soak_test'),
      resultStatus: _string(json['result_status'], 'blocked'),
      realOrderSubmitted: _bool(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _bool(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _bool(json['manual_submit_called']) ?? false,
      orderCancelCalled: _bool(json['order_cancel_called']) ?? false,
      actionTaken: _string(json['action_taken'], 'none'),
      orchestratorRunId: _nullableInt(json['orchestrator_run_id']),
      brokerSyncHealth: _string(json['broker_sync_health'], 'unknown'),
      automationModeEffectiveStatus:
          _string(json['automation_mode_effective_status'], 'unknown'),
      productionReadinessStatus:
          _string(json['production_readiness_status'], 'unknown'),
      killRulesEvaluated: _rules(json['kill_rules_evaluated']),
      killRulesTriggered: _rules(json['kill_rules_triggered']),
      killLatchActive: _bool(json['kill_latch_active']) ?? false,
      cycleCountToday: _int(json['cycle_count_today']),
      actionCountToday: _int(json['action_count_today']),
      consecutiveFailureCount: _int(json['consecutive_failure_count']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      blockingReasons: _strings(json['blocking_reasons']),
      warningReasons: _strings(json['warning_reasons']),
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

List<AutomationKillRule> _rules(Object? value) {
  if (value is! List) return const [];
  return List<AutomationKillRule>.unmodifiable([
    for (final item in value) AutomationKillRule.fromJson(item),
  ]);
}

