import 'auto_exit_candidate.dart';

class PositionManagementDryRun {
  const PositionManagementDryRun({
    required this.runId,
    required this.generatedAt,
    required this.provider,
    required this.market,
    required this.triggerSource,
    required this.dryRunOnly,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.positionsChecked,
    required this.exitCandidateCount,
    required this.criticalCandidateCount,
    required this.warningCandidateCount,
    required this.simulatedSellPreflightCount,
    required this.blockedPreflightCount,
    required this.syncRequiredCount,
    required this.duplicateSellConflictCount,
    required this.resultStatus,
    required this.primaryReason,
    required this.riskFlags,
    required this.gatingNotes,
    required this.candidates,
    required this.sellPreflightResults,
    required this.nextSafeActions,
    required this.priority,
    required this.entryOrdersAllowed,
    required this.exitOrdersAllowed,
    required this.dryRunMonitoringOnly,
    required this.schedulerEnabled,
    required this.schedulerDryRunOnly,
    required this.schedulerAllowLiveOrders,
    required this.safety,
    required this.rawPayload,
  });

  factory PositionManagementDryRun.fromJson(Map<String, dynamic> json) {
    final rawCandidates = json['candidates'];
    final rawPreflights = json['sell_preflight_results'];
    return PositionManagementDryRun(
      runId: _nullableInt(json['run_id']),
      generatedAt: _nullableDateTime(json['generated_at']),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      triggerSource: _string(json['trigger_source'], ''),
      dryRunOnly: json['dry_run_only'] != false,
      realOrderSubmitted: json['real_order_submitted'] == true,
      brokerSubmitCalled: json['broker_submit_called'] == true,
      manualSubmitCalled: json['manual_submit_called'] == true,
      positionsChecked: _int(json['positions_checked']),
      exitCandidateCount: _int(json['exit_candidate_count']),
      criticalCandidateCount: _int(json['critical_candidate_count']),
      warningCandidateCount: _int(json['warning_candidate_count']),
      simulatedSellPreflightCount: _int(json['simulated_sell_preflight_count']),
      blockedPreflightCount: _int(json['blocked_preflight_count']),
      syncRequiredCount: _int(json['sync_required_count']),
      duplicateSellConflictCount: _int(json['duplicate_sell_conflict_count']),
      resultStatus: _string(json['result_status'], 'unknown'),
      primaryReason: _nullableString(json['primary_reason']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      candidates: rawCandidates is List
          ? [
              for (final item in rawCandidates)
                if (item is Map)
                  AutoExitCandidate.fromJson(Map<String, dynamic>.from(item)),
            ]
          : const [],
      sellPreflightResults: rawPreflights is List
          ? [
              for (final item in rawPreflights)
                if (item is Map) Map<String, dynamic>.from(item),
            ]
          : const [],
      nextSafeActions: _strings(json['next_safe_actions']),
      priority: _string(json['priority'], 'positions_first'),
      entryOrdersAllowed: json['entry_orders_allowed'] == true,
      exitOrdersAllowed: json['exit_orders_allowed'] == true,
      dryRunMonitoringOnly: json['dry_run_monitoring_only'] != false,
      schedulerEnabled: json['scheduler_enabled'] == true,
      schedulerDryRunOnly: json['scheduler_dry_run_only'] != false,
      schedulerAllowLiveOrders: json['scheduler_allow_live_orders'] == true,
      safety: _map(json['safety']),
      rawPayload: Map<String, dynamic>.from(json),
    );
  }

  final int? runId;
  final DateTime? generatedAt;
  final String provider;
  final String market;
  final String triggerSource;
  final bool dryRunOnly;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final int positionsChecked;
  final int exitCandidateCount;
  final int criticalCandidateCount;
  final int warningCandidateCount;
  final int simulatedSellPreflightCount;
  final int blockedPreflightCount;
  final int syncRequiredCount;
  final int duplicateSellConflictCount;
  final String resultStatus;
  final String? primaryReason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<AutoExitCandidate> candidates;
  final List<Map<String, dynamic>> sellPreflightResults;
  final List<String> nextSafeActions;
  final String priority;
  final bool entryOrdersAllowed;
  final bool exitOrdersAllowed;
  final bool dryRunMonitoringOnly;
  final bool schedulerEnabled;
  final bool schedulerDryRunOnly;
  final bool schedulerAllowLiveOrders;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> rawPayload;
}

String _string(dynamic value, String fallback) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? fallback : text;
}

String? _nullableString(dynamic value) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? null : text;
}

int _int(dynamic value) => _nullableInt(value) ?? 0;

int? _nullableInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

DateTime? _nullableDateTime(dynamic value) {
  final text = value?.toString().trim() ?? '';
  if (text.isEmpty) return null;
  return DateTime.tryParse(text);
}

Map<String, dynamic> _map(dynamic value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

List<String> _strings(dynamic value) {
  if (value is List) {
    return [
      for (final item in value)
        if (item != null) item.toString()
    ];
  }
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? const [] : [text];
}
