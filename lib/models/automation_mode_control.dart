class AutomationModePendingOrderBlocker {
  const AutomationModePendingOrderBlocker({
    this.orderId,
    this.symbol,
    this.side,
    required this.internalStatus,
    required this.syncRequired,
    required this.reason,
  });

  final int? orderId;
  final String? symbol;
  final String? side;
  final String internalStatus;
  final bool syncRequired;
  final String reason;

  factory AutomationModePendingOrderBlocker.fromJson(Object? value) {
    if (value is! Map) {
      return const AutomationModePendingOrderBlocker(
        internalStatus: '',
        syncRequired: false,
        reason: 'pending_order',
      );
    }
    final json = Map<String, dynamic>.from(value);
    return AutomationModePendingOrderBlocker(
      orderId: _nullableInt(json['order_id']),
      symbol: _nullableString(json['symbol']),
      side: _nullableString(json['side']),
      internalStatus: _string(json['internal_status'], ''),
      syncRequired: _bool(json['sync_required']) ?? false,
      reason: _string(json['reason'], 'pending_order'),
    );
  }
}

class AutomationModeControlStatus {
  const AutomationModeControlStatus({
    required this.generatedAt,
    required this.automationMode,
    required this.modeLabel,
    required this.modeDescription,
    required this.modeRequiresManualReview,
    required this.effectiveStatus,
    required this.canRunMonitoring,
    required this.canRunDryRun,
    required this.canAttemptPhase1Live,
    required this.canSubmitLiveOrder,
    required this.killSwitch,
    required this.dryRun,
    required this.kisEnabled,
    required this.kisRealOrderEnabled,
    required this.productionReadinessStatus,
    required this.brokerSyncHealth,
    required this.brokerSyncBlockingReasons,
    required this.brokerSyncIssueCount,
    required this.brokerSyncWatchdog,
    required this.portfolioOrchestratorEnabled,
    required this.portfolioOrchestratorAllowLiveOrders,
    required this.positionManagementSchedulerEnabled,
    required this.autoBuyLivePhase1Enabled,
    required this.autoSellLivePhase1Enabled,
    required this.schedulerEnabled,
    required this.pendingOrderBlockers,
    required this.syncRequiredCount,
    required this.criticalExitCandidateCount,
    required this.dailyTradeLimitRemaining,
    required this.blockingReasons,
    required this.warningReasons,
    required this.nextSafeAction,
    required this.safetyFlags,
    required this.modules,
    this.modeUpdatedAt,
    this.modeUpdatedBy,
    this.modeReason,
  });

  final DateTime generatedAt;
  final String automationMode;
  final String modeLabel;
  final String modeDescription;
  final DateTime? modeUpdatedAt;
  final String? modeUpdatedBy;
  final String? modeReason;
  final bool modeRequiresManualReview;
  final String effectiveStatus;
  final bool canRunMonitoring;
  final bool canRunDryRun;
  final bool canAttemptPhase1Live;
  final bool canSubmitLiveOrder;
  final bool killSwitch;
  final bool dryRun;
  final bool kisEnabled;
  final bool kisRealOrderEnabled;
  final String productionReadinessStatus;
  final String brokerSyncHealth;
  final List<String> brokerSyncBlockingReasons;
  final int brokerSyncIssueCount;
  final Map<String, dynamic> brokerSyncWatchdog;
  final bool portfolioOrchestratorEnabled;
  final bool portfolioOrchestratorAllowLiveOrders;
  final bool positionManagementSchedulerEnabled;
  final bool autoBuyLivePhase1Enabled;
  final bool autoSellLivePhase1Enabled;
  final bool schedulerEnabled;
  final List<AutomationModePendingOrderBlocker> pendingOrderBlockers;
  final int syncRequiredCount;
  final int criticalExitCandidateCount;
  final int dailyTradeLimitRemaining;
  final List<String> blockingReasons;
  final List<String> warningReasons;
  final String nextSafeAction;
  final Map<String, dynamic> safetyFlags;
  final Map<String, dynamic> modules;

  bool get hasBlockingReasons => blockingReasons.isNotEmpty;
  bool get hasWarnings => warningReasons.isNotEmpty;
  bool get liveEligible => canSubmitLiveOrder;
  bool get liveBlocked =>
      automationMode == 'phase1_live_ready' && !liveEligible;

  factory AutomationModeControlStatus.fromJson(Map<String, dynamic> json) {
    return AutomationModeControlStatus(
      generatedAt: _dateTime(json['generated_at']) ?? DateTime.now(),
      automationMode: _string(json['automation_mode'], 'off'),
      modeLabel: _string(json['mode_label'], 'Automation Off'),
      modeDescription: _string(json['mode_description'], ''),
      modeUpdatedAt: _dateTime(json['mode_updated_at']),
      modeUpdatedBy: _nullableString(json['mode_updated_by']),
      modeReason: _nullableString(json['mode_reason']),
      modeRequiresManualReview:
          _bool(json['mode_requires_manual_review']) ?? true,
      effectiveStatus: _string(json['effective_status'], 'off'),
      canRunMonitoring: _bool(json['can_run_monitoring']) ?? false,
      canRunDryRun: _bool(json['can_run_dry_run']) ?? false,
      canAttemptPhase1Live: _bool(json['can_attempt_phase1_live']) ?? false,
      canSubmitLiveOrder: _bool(json['can_submit_live_order']) ?? false,
      killSwitch: _bool(json['kill_switch']) ?? false,
      dryRun: _bool(json['dry_run']) ?? true,
      kisEnabled: _bool(json['kis_enabled']) ?? false,
      kisRealOrderEnabled: _bool(json['kis_real_order_enabled']) ?? false,
      productionReadinessStatus:
          _string(json['production_readiness_status'], 'unknown'),
      brokerSyncHealth: _string(json['broker_sync_health'], 'unknown'),
      brokerSyncBlockingReasons: _strings(
        json['broker_sync_blocking_reasons'],
      ),
      brokerSyncIssueCount: _int(json['broker_sync_issue_count']),
      brokerSyncWatchdog: _map(json['broker_sync_watchdog']),
      portfolioOrchestratorEnabled:
          _bool(json['portfolio_orchestrator_enabled']) ?? false,
      portfolioOrchestratorAllowLiveOrders:
          _bool(json['portfolio_orchestrator_allow_live_orders']) ?? false,
      positionManagementSchedulerEnabled:
          _bool(json['position_management_scheduler_enabled']) ?? false,
      autoBuyLivePhase1Enabled:
          _bool(json['auto_buy_live_phase1_enabled']) ?? false,
      autoSellLivePhase1Enabled:
          _bool(json['auto_sell_live_phase1_enabled']) ?? false,
      schedulerEnabled: _bool(json['scheduler_enabled']) ?? false,
      pendingOrderBlockers: _blockers(json['pending_order_blockers']),
      syncRequiredCount: _int(json['sync_required_count']),
      criticalExitCandidateCount: _int(json['critical_exit_candidate_count']),
      dailyTradeLimitRemaining: _int(json['daily_trade_limit_remaining']),
      blockingReasons: _strings(json['blocking_reasons']),
      warningReasons: _strings(json['warning_reasons']),
      nextSafeAction: _string(json['next_safe_action'], 'automation_is_off'),
      safetyFlags: _map(json['safety_flags']),
      modules: _map(json['modules']),
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

List<AutomationModePendingOrderBlocker> _blockers(Object? value) {
  if (value is! List) return const [];
  return List<AutomationModePendingOrderBlocker>.unmodifiable([
    for (final item in value) AutomationModePendingOrderBlocker.fromJson(item),
  ]);
}
