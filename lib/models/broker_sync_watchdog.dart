class BrokerSyncWatchdogIssue {
  const BrokerSyncWatchdogIssue({
    required this.issueId,
    required this.issueType,
    required this.severity,
    required this.provider,
    required this.market,
    required this.detectedAt,
    required this.automationBlocking,
    required this.recommendedAction,
    required this.reason,
    required this.sanitizedContext,
    this.symbol,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    this.ageMinutes,
    this.localStatus,
    this.brokerStatus,
    this.localQuantity,
    this.brokerQuantity,
  });

  final String issueId;
  final String issueType;
  final String severity;
  final String provider;
  final String market;
  final String? symbol;
  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final DateTime detectedAt;
  final double? ageMinutes;
  final String? localStatus;
  final String? brokerStatus;
  final double? localQuantity;
  final double? brokerQuantity;
  final bool automationBlocking;
  final String recommendedAction;
  final String reason;
  final Map<String, dynamic> sanitizedContext;

  bool get critical => severity == 'critical';
  bool get warning => severity == 'warning';

  factory BrokerSyncWatchdogIssue.fromJson(Object? value) {
    if (value is! Map) {
      return BrokerSyncWatchdogIssue(
        issueId: 'unknown',
        issueType: 'unknown',
        severity: 'info',
        provider: 'kis',
        market: 'KR',
        detectedAt: DateTime.now(),
        automationBlocking: false,
        recommendedAction: 'manual_review',
        reason: 'unknown',
        sanitizedContext: const {},
      );
    }
    final json = Map<String, dynamic>.from(value);
    return BrokerSyncWatchdogIssue(
      issueId: _string(json['issue_id'], 'unknown'),
      issueType: _string(json['issue_type'], 'unknown'),
      severity: _string(json['severity'], 'info'),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      symbol: _nullableString(json['symbol']),
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      detectedAt: _dateTime(json['detected_at']) ?? DateTime.now(),
      ageMinutes: _nullableDouble(json['age_minutes']),
      localStatus: _nullableString(json['local_status']),
      brokerStatus: _nullableString(json['broker_status']),
      localQuantity: _nullableDouble(json['local_quantity']),
      brokerQuantity: _nullableDouble(json['broker_quantity']),
      automationBlocking: _bool(json['automation_blocking']) ?? false,
      recommendedAction: _string(json['recommended_action'], 'manual_review'),
      reason: _string(json['reason'], 'unknown'),
      sanitizedContext: _map(json['sanitized_context']),
    );
  }
}

class BrokerSyncWatchdogResult {
  const BrokerSyncWatchdogResult({
    required this.generatedAt,
    required this.provider,
    required this.market,
    required this.watchdogEnabled,
    required this.automationBlockedBySync,
    required this.syncHealth,
    required this.canRunAutomation,
    required this.shouldBlockAutoBuy,
    required this.shouldBlockAutoSell,
    required this.shouldBlockOrchestrator,
    required this.localOrderCount,
    required this.openLocalOrderCount,
    required this.brokerOpenOrderCount,
    required this.staleLocalOrderCount,
    required this.pendingSyncOrderCount,
    required this.missingBrokerIdCount,
    required this.missingKisOdnoCount,
    required this.brokerUnmatchedOrderCount,
    required this.localUnmatchedOrderCount,
    required this.stalePositionSnapshotCount,
    required this.positionMismatchCount,
    required this.cashSnapshotStale,
    required this.issues,
    required this.summary,
    required this.riskFlags,
    required this.gatingNotes,
    required this.blockingReasons,
    required this.warningReasons,
    required this.nextSafeAction,
    required this.safetyFlags,
    this.runId,
    this.lastSuccessfulSyncAt,
    this.lastWatchdogRunAt,
  });

  final int? runId;
  final DateTime generatedAt;
  final String provider;
  final String market;
  final bool watchdogEnabled;
  final bool automationBlockedBySync;
  final String syncHealth;
  final bool canRunAutomation;
  final bool shouldBlockAutoBuy;
  final bool shouldBlockAutoSell;
  final bool shouldBlockOrchestrator;
  final int localOrderCount;
  final int openLocalOrderCount;
  final int brokerOpenOrderCount;
  final int staleLocalOrderCount;
  final int pendingSyncOrderCount;
  final int missingBrokerIdCount;
  final int missingKisOdnoCount;
  final int brokerUnmatchedOrderCount;
  final int localUnmatchedOrderCount;
  final int stalePositionSnapshotCount;
  final int positionMismatchCount;
  final bool cashSnapshotStale;
  final DateTime? lastSuccessfulSyncAt;
  final DateTime? lastWatchdogRunAt;
  final List<BrokerSyncWatchdogIssue> issues;
  final String summary;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<String> blockingReasons;
  final List<String> warningReasons;
  final String nextSafeAction;
  final Map<String, dynamic> safetyFlags;

  bool get healthy => syncHealth == 'healthy';
  bool get warning => syncHealth == 'warning';
  bool get unsafe => syncHealth == 'unsafe';
  bool get unknown => syncHealth == 'unknown';

  factory BrokerSyncWatchdogResult.fromJson(Map<String, dynamic> json) {
    return BrokerSyncWatchdogResult(
      runId: _nullableInt(json['run_id']),
      generatedAt: _dateTime(json['generated_at']) ?? DateTime.now(),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      watchdogEnabled: _bool(json['watchdog_enabled']) ?? false,
      automationBlockedBySync:
          _bool(json['automation_blocked_by_sync']) ?? false,
      syncHealth: _string(json['sync_health'], 'unknown'),
      canRunAutomation: _bool(json['can_run_automation']) ?? false,
      shouldBlockAutoBuy: _bool(json['should_block_auto_buy']) ?? false,
      shouldBlockAutoSell: _bool(json['should_block_auto_sell']) ?? false,
      shouldBlockOrchestrator:
          _bool(json['should_block_orchestrator']) ?? false,
      localOrderCount: _int(json['local_order_count']),
      openLocalOrderCount: _int(json['open_local_order_count']),
      brokerOpenOrderCount: _int(json['broker_open_order_count']),
      staleLocalOrderCount: _int(json['stale_local_order_count']),
      pendingSyncOrderCount: _int(json['pending_sync_order_count']),
      missingBrokerIdCount: _int(json['missing_broker_id_count']),
      missingKisOdnoCount: _int(json['missing_kis_odno_count']),
      brokerUnmatchedOrderCount: _int(json['broker_unmatched_order_count']),
      localUnmatchedOrderCount: _int(json['local_unmatched_order_count']),
      stalePositionSnapshotCount: _int(
        json['stale_position_snapshot_count'],
      ),
      positionMismatchCount: _int(json['position_mismatch_count']),
      cashSnapshotStale: _bool(json['cash_snapshot_stale']) ?? false,
      lastSuccessfulSyncAt: _dateTime(json['last_successful_sync_at']),
      lastWatchdogRunAt: _dateTime(json['last_watchdog_run_at']),
      issues: _issues(json['issues']),
      summary: _string(json['summary'], ''),
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

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString().trim().replaceAll(',', ''));
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

List<BrokerSyncWatchdogIssue> _issues(Object? value) {
  if (value is! List) return const [];
  return List<BrokerSyncWatchdogIssue>.unmodifiable([
    for (final item in value) BrokerSyncWatchdogIssue.fromJson(item),
  ]);
}
