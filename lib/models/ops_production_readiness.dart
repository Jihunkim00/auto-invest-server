class OpsProductionReadiness {
  const OpsProductionReadiness({
    required this.mode,
    required this.readinessOnly,
    required this.productionReady,
    required this.liveTradingReady,
    required this.paperOrDryRunReady,
    required this.summary,
    required this.runtime,
    required this.kis,
    required this.scheduler,
    required this.risk,
    required this.today,
    required this.recentActivity,
    required this.safetyChecks,
    required this.blockingIssues,
    required this.warnings,
    required this.recommendedActions,
    required this.documentation,
    required this.diagnostics,
    required this.rawPayload,
  });

  factory OpsProductionReadiness.fromJson(Map<String, dynamic> json) {
    return OpsProductionReadiness(
      mode: _stringValue(json['mode'], fallback: 'ops_production_readiness'),
      readinessOnly: _boolValue(json['readiness_only']) ?? true,
      productionReady: _boolValue(json['production_ready']) ?? false,
      liveTradingReady: _boolValue(json['live_trading_ready']) ?? false,
      paperOrDryRunReady: _boolValue(json['paper_or_dry_run_ready']) ?? false,
      summary: _dynamicMap(json['summary']),
      runtime: _dynamicMap(json['runtime']),
      kis: _dynamicMap(json['kis']),
      scheduler: _dynamicMap(json['scheduler']),
      risk: _dynamicMap(json['risk']),
      today: _dynamicMap(json['today']),
      recentActivity: _mapList(json['recent_activity']),
      safetyChecks:
          _mapList(json['safety_checks']).map(OpsSafetyCheck.fromJson).toList(),
      blockingIssues: _stringList(json['blocking_issues']),
      warnings: _stringList(json['warnings']),
      recommendedActions: _stringList(json['recommended_actions']),
      documentation: _dynamicMap(json['documentation']),
      diagnostics: _dynamicMap(json['diagnostics']),
      rawPayload: _dynamicMap(json),
    );
  }

  final String mode;
  final bool readinessOnly;
  final bool productionReady;
  final bool liveTradingReady;
  final bool paperOrDryRunReady;
  final Map<String, dynamic> summary;
  final Map<String, dynamic> runtime;
  final Map<String, dynamic> kis;
  final Map<String, dynamic> scheduler;
  final Map<String, dynamic> risk;
  final Map<String, dynamic> today;
  final List<Map<String, dynamic>> recentActivity;
  final List<OpsSafetyCheck> safetyChecks;
  final List<String> blockingIssues;
  final List<String> warnings;
  final List<String> recommendedActions;
  final Map<String, dynamic> documentation;
  final Map<String, dynamic> diagnostics;
  final Map<String, dynamic> rawPayload;

  String get overallStatus =>
      _stringValue(summary['overall_status'], fallback: 'UNKNOWN');

  bool get dryRun => _boolValue(summary['dry_run']) ?? true;
  bool get killSwitch => _boolValue(summary['kill_switch']) ?? false;
  bool get kisRealOrderEnabled =>
      _boolValue(summary['kis_real_order_enabled']) ?? false;
  bool get schedulerRealOrdersEnabled =>
      _boolValue(scheduler['scheduler_real_orders_allowed']) ??
      _boolValue(summary['kis_scheduler_allow_real_orders']) ??
      false;
  bool get schedulerSellEnabled =>
      _boolValue(summary['kis_scheduler_sell_enabled']) ??
      _boolValue(scheduler['scheduler_sell_enabled']) ??
      false;
  bool get schedulerBuyEnabled =>
      _boolValue(summary['kis_scheduler_buy_enabled']) ??
      _boolValue(scheduler['scheduler_buy_enabled']) ??
      false;
  bool get liveAutoSellEnabled =>
      _boolValue(summary['kis_live_auto_sell_enabled']) ?? false;
  bool get liveAutoBuyEnabled =>
      _boolValue(summary['kis_live_auto_buy_enabled']) ?? false;
  int get todayBrokerSubmits => _intValue(today['broker_submits']);
  int get todayOrderCount => _intValue(today['order_logs_created']);
  int get criticalIssueCount => _intValue(summary['critical_issue_count']);
  int get warningCount => _intValue(summary['warning_count']);
  int get totalRunsToday => _intValue(today['total_runs']);
  int get blockedCountToday => _intValue(today['blocked_count']);
  int get failedCountToday => _intValue(today['failed_count']);

  String get topBlockReason {
    final reasons = today['top_block_reasons'];
    if (reasons is List && reasons.isNotEmpty && reasons.first is Map) {
      final first = Map<String, dynamic>.from(reasons.first as Map);
      final reason = first['reason']?.toString().trim();
      if (reason != null && reason.isNotEmpty) return reason;
    }
    return 'n/a';
  }

  OpsSafetyCheck? check(String key) {
    for (final item in safetyChecks) {
      if (item.key == key) return item;
    }
    return null;
  }

  bool get hasRecentDryRun => recentActivity.any((item) {
        final mode = item['mode']?.toString().toLowerCase() ?? '';
        final trigger = item['trigger_source']?.toString().toLowerCase() ?? '';
        return mode.contains('dry_run') || trigger.contains('dry_run');
      });

  bool get hasRecentSchedulerReview => recentActivity.any((item) {
        final mode = item['mode']?.toString().toLowerCase() ?? '';
        final trigger = item['trigger_source']?.toString().toLowerCase() ?? '';
        return mode.contains('guarded_sell') ||
            mode.contains('guarded_buy') ||
            trigger.contains('guarded_sell') ||
            trigger.contains('guarded_buy');
      });
}

class OpsSafetyCheck {
  const OpsSafetyCheck({
    required this.key,
    required this.label,
    required this.status,
    required this.value,
    required this.message,
    required this.recommendedAction,
  });

  factory OpsSafetyCheck.fromJson(Map<String, dynamic> json) {
    return OpsSafetyCheck(
      key: _stringValue(json['key'], fallback: ''),
      label: _stringValue(json['label'], fallback: ''),
      status: _stringValue(json['status'], fallback: 'INFO').toUpperCase(),
      value: json['value'],
      message: _stringValue(json['message'], fallback: ''),
      recommendedAction: _stringValue(json['recommended_action'], fallback: ''),
    );
  }

  final String key;
  final String label;
  final String status;
  final Object? value;
  final String message;
  final String recommendedAction;
}

Map<String, dynamic> _dynamicMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

List<Map<String, dynamic>> _mapList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map) Map<String, dynamic>.from(item)
  ];
}

String _stringValue(Object? value, {required String fallback}) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return fallback;
  return text;
}

int _intValue(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
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

List<String> _stringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}
