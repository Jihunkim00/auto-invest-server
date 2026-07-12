class PortfolioOrchestratorChecklistItem {
  const PortfolioOrchestratorChecklistItem({
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

  bool get failed => !ok || blocking || status == 'fail';

  factory PortfolioOrchestratorChecklistItem.fromJson(Object? value) {
    if (value is! Map) {
      return const PortfolioOrchestratorChecklistItem(
        key: 'check',
        status: 'pass',
        ok: true,
        blocking: false,
      );
    }
    final json = Map<String, dynamic>.from(value);
    final ok = _bool(json['ok']) ?? json['status'] == 'pass';
    return PortfolioOrchestratorChecklistItem(
      key: _string(json['key'], 'check'),
      status: _string(json['status'], ok ? 'pass' : 'fail'),
      ok: ok,
      blocking: _bool(json['blocking']) ?? !ok,
      reason: _nullableString(json['reason']),
      detail: _nullableString(json['detail']),
    );
  }
}

/// A compact, tolerant view of one service result embedded in an orchestrator
/// response. The raw payload is retained so new backend audit fields remain
/// available without weakening the typed safety fields used by the UI.
class PortfolioOrchestratorStepResult {
  const PortfolioOrchestratorStepResult({
    required this.raw,
    this.resultStatus,
    this.primaryReason,
    this.primaryBlockReason,
    this.nextSafeAction,
    this.selectedSymbol,
    this.realOrderSubmitted = false,
    this.brokerSubmitCalled = false,
    this.manualSubmitCalled = false,
  });

  final Map<String, dynamic> raw;
  final String? resultStatus;
  final String? primaryReason;
  final String? primaryBlockReason;
  final String? nextSafeAction;
  final String? selectedSymbol;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;

  String? get reason => primaryBlockReason ?? primaryReason;

  factory PortfolioOrchestratorStepResult.fromJson(Map<String, dynamic> json) {
    return PortfolioOrchestratorStepResult(
      raw: Map<String, dynamic>.unmodifiable(json),
      resultStatus: _nullableString(
        json['result_status'] ?? json['status'] ?? json['action'],
      ),
      primaryReason: _nullableString(json['primary_reason']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      nextSafeAction: _nullableString(
        json['next_safe_action'] ??
            (json['next_safe_actions'] is List &&
                    (json['next_safe_actions'] as List).isNotEmpty
                ? (json['next_safe_actions'] as List).first
                : null),
      ),
      selectedSymbol: _nullableString(
        json['selected_symbol'] ?? json['symbol'],
      ),
      realOrderSubmitted: _bool(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _bool(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _bool(json['manual_submit_called']) ?? false,
    );
  }
}

class PortfolioOrchestratorResult {
  const PortfolioOrchestratorResult({
    required this.generatedAt,
    required this.provider,
    required this.market,
    required this.triggerSource,
    required this.orchestratorEnabled,
    required this.allowLiveOrders,
    required this.mode,
    required this.positionsFirst,
    required this.resultStatus,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.actionTaken,
    required this.maxActionsPerRun,
    required this.dailyTradeLimitUsed,
    required this.dailyTradeLimitRemaining,
    required this.syncRequiredCount,
    required this.criticalExitCandidateCount,
    required this.pendingOrderConflictCount,
    required this.brokerSyncHealth,
    required this.brokerSyncBlockingReasons,
    required this.brokerSyncIssueCount,
    required this.brokerSyncWatchdog,
    required this.soakKillLatchActive,
    required this.killRulesTriggered,
    required this.riskFlags,
    required this.gatingNotes,
    required this.checklist,
    required this.nextSafeAction,
    required this.safety,
    this.runId,
    this.positionManagementResult,
    this.autoSellPhase1Result,
    this.autoBuyPhase1Result,
    this.skippedBuyReason,
    this.skippedSellReason,
    this.productionReadinessStatus,
    this.soakKillLatchReason,
    this.primaryBlockReason,
    this.selectedSymbol,
    this.selectedCandidateId,
    this.selectedPromotionId,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
  });

  final int? runId;
  final DateTime generatedAt;
  final String provider;
  final String market;
  final String triggerSource;
  final bool orchestratorEnabled;
  final bool allowLiveOrders;
  final String mode;
  final bool positionsFirst;
  final String resultStatus;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String actionTaken;
  final int maxActionsPerRun;
  final PortfolioOrchestratorStepResult? positionManagementResult;
  final PortfolioOrchestratorStepResult? autoSellPhase1Result;
  final PortfolioOrchestratorStepResult? autoBuyPhase1Result;
  final String? skippedBuyReason;
  final String? skippedSellReason;
  final int dailyTradeLimitUsed;
  final int dailyTradeLimitRemaining;
  final int syncRequiredCount;
  final int criticalExitCandidateCount;
  final int pendingOrderConflictCount;
  final String brokerSyncHealth;
  final List<String> brokerSyncBlockingReasons;
  final int brokerSyncIssueCount;
  final Map<String, dynamic> brokerSyncWatchdog;
  final bool soakKillLatchActive;
  final String? soakKillLatchReason;
  final List<String> killRulesTriggered;
  final String? productionReadinessStatus;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<PortfolioOrchestratorChecklistItem> checklist;
  final String? primaryBlockReason;
  final String nextSafeAction;
  final Map<String, dynamic> safety;
  final String? selectedSymbol;
  final String? selectedCandidateId;
  final int? selectedPromotionId;
  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;

  bool get disabled => !orchestratorEnabled || resultStatus == 'disabled';

  bool get blocked =>
      resultStatus == 'blocked' ||
      resultStatus == 'error' ||
      resultStatus == 'rejected';

  bool get sellSubmitted =>
      realOrderSubmitted &&
      (actionTaken == 'auto_sell_phase1' || resultStatus == 'sell_submitted');

  bool get buySubmitted =>
      realOrderSubmitted &&
      (actionTaken == 'auto_buy_phase1' || resultStatus == 'buy_submitted');

  bool get noAction => !sellSubmitted && !buySubmitted;

  bool get completed =>
      resultStatus == 'completed_no_action' ||
      resultStatus == 'dry_run_completed' ||
      sellSubmitted ||
      buySubmitted;

  factory PortfolioOrchestratorResult.fromJson(Map<String, dynamic> json) {
    return PortfolioOrchestratorResult(
      runId: _nullableInt(json['run_id']),
      generatedAt: _dateTime(json['generated_at']) ?? DateTime.now(),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      triggerSource: _string(json['trigger_source'], 'status'),
      orchestratorEnabled: _bool(json['orchestrator_enabled']) ?? false,
      allowLiveOrders: _bool(json['allow_live_orders']) ?? false,
      mode: _string(json['mode'], 'dry_run_monitoring'),
      positionsFirst: _bool(json['positions_first']) ?? true,
      resultStatus: _string(json['result_status'], 'disabled'),
      realOrderSubmitted: _bool(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _bool(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _bool(json['manual_submit_called']) ?? false,
      actionTaken: _string(json['action_taken'], 'none'),
      maxActionsPerRun: _int(json['max_actions_per_run'], fallback: 1),
      positionManagementResult: _step(json['position_management_result']),
      autoSellPhase1Result: _step(json['auto_sell_phase1_result']),
      autoBuyPhase1Result: _step(json['auto_buy_phase1_result']),
      skippedBuyReason: _nullableString(json['skipped_buy_reason']),
      skippedSellReason: _nullableString(json['skipped_sell_reason']),
      dailyTradeLimitUsed: _int(json['daily_trade_limit_used']),
      dailyTradeLimitRemaining: _int(json['daily_trade_limit_remaining']),
      syncRequiredCount: _int(json['sync_required_count']),
      criticalExitCandidateCount: _int(json['critical_exit_candidate_count']),
      pendingOrderConflictCount: _int(json['pending_order_conflict_count']),
      brokerSyncHealth: _string(json['broker_sync_health'], 'unknown'),
      brokerSyncBlockingReasons: _strings(
        json['broker_sync_blocking_reasons'],
      ),
      brokerSyncIssueCount: _int(json['broker_sync_issue_count']),
      brokerSyncWatchdog: _map(json['broker_sync_watchdog']),
      soakKillLatchActive: _bool(json['soak_kill_latch_active']) ?? false,
      soakKillLatchReason: _nullableString(json['soak_kill_latch_reason']),
      killRulesTriggered: _strings(json['kill_rules_triggered']),
      productionReadinessStatus:
          _nullableString(json['production_readiness_status']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      checklist: _checklist(json['checklist']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      nextSafeAction: _string(json['next_safe_action'], 'review_safety_gates'),
      safety: _map(json['safety']),
      selectedSymbol: _nullableString(json['selected_symbol']),
      selectedCandidateId: _nullableString(json['selected_candidate_id']),
      selectedPromotionId: _nullableInt(json['selected_promotion_id']),
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
    );
  }
}

PortfolioOrchestratorStepResult? _step(Object? value) {
  if (value is! Map) return null;
  return PortfolioOrchestratorStepResult.fromJson(
    Map<String, dynamic>.from(value),
  );
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
      ? Map<String, dynamic>.unmodifiable(
          Map<String, dynamic>.from(value),
        )
      : const <String, dynamic>{};
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return List<String>.unmodifiable([
    for (final item in value)
      if (item.toString().trim().isNotEmpty) item.toString(),
  ]);
}

List<PortfolioOrchestratorChecklistItem> _checklist(Object? value) {
  if (value is! List) return const [];
  return List<PortfolioOrchestratorChecklistItem>.unmodifiable([
    for (final item in value) PortfolioOrchestratorChecklistItem.fromJson(item),
  ]);
}
