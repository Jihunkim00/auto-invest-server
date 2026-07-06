class OpsProductionReadiness {
  const OpsProductionReadiness({
    required this.generatedAt,
    required this.timezone,
    required this.provider,
    required this.market,
    required this.overallStatus,
    required this.readinessScore,
    required this.summary,
    required this.checklist,
    required this.blockingReasons,
    required this.warnings,
    required this.nextSafeActions,
    required this.safetyFlags,
    required this.details,
    required this.rawPayload,
  });

  factory OpsProductionReadiness.fromJson(Map<String, dynamic> json) {
    final rawSummary = _dynamicMap(json['summary']);
    final checklist = _mapList(json['checklist']).isNotEmpty
        ? _mapList(json['checklist'])
            .map(OpsReadinessChecklistItem.fromJson)
            .toList()
        : _mapList(json['safety_checks'])
            .map(OpsReadinessChecklistItem.fromLegacyJson)
            .toList();
    return OpsProductionReadiness(
      generatedAt: _dateTimeValue(json['generated_at']),
      timezone: _stringValue(json['timezone'], fallback: 'Asia/Seoul'),
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      overallStatus: _normalizeOverallStatus(
        json['overall_status'] ?? rawSummary['overall_status'],
      ),
      readinessScore: _intValue(json['readiness_score']),
      summary: OpsProductionReadinessSummary.fromJson(rawSummary),
      checklist: checklist,
      blockingReasons: _stringList(
        json['blocking_reasons'] ?? json['blocking_issues'],
      ),
      warnings: _stringList(json['warnings']),
      nextSafeActions: _stringList(
        json['next_safe_actions'] ?? json['recommended_actions'],
      ),
      safetyFlags: _dynamicMap(json['safety_flags']),
      details: _dynamicMap(json['details']),
      rawPayload: _dynamicMap(json),
    );
  }

  final DateTime? generatedAt;
  final String timezone;
  final String provider;
  final String market;
  final String overallStatus;
  final int readinessScore;
  final OpsProductionReadinessSummary summary;
  final List<OpsReadinessChecklistItem> checklist;
  final List<String> blockingReasons;
  final List<String> warnings;
  final List<String> nextSafeActions;
  final Map<String, dynamic> safetyFlags;
  final Map<String, dynamic> details;
  final Map<String, dynamic> rawPayload;

  String get mode =>
      _stringValue(rawPayload['mode'], fallback: 'ops_production_readiness');
  bool get readinessOnly => _boolValue(rawPayload['readiness_only']) ?? true;
  bool get productionReady =>
      _boolValue(rawPayload['production_ready']) ?? overallStatus == 'ready';
  bool get liveTradingReady =>
      _boolValue(rawPayload['live_trading_ready']) ??
      summary.canUseGuardedLiveBuy || summary.canUseGuardedLiveSell;
  bool get paperOrDryRunReady =>
      _boolValue(rawPayload['paper_or_dry_run_ready']) ?? dryRun;

  Map<String, dynamic> get runtime => _dynamicMap(rawPayload['runtime']);
  Map<String, dynamic> get kis => _dynamicMap(rawPayload['kis']);
  Map<String, dynamic> get scheduler => _dynamicMap(rawPayload['scheduler']);
  Map<String, dynamic> get risk => _dynamicMap(rawPayload['risk']);
  Map<String, dynamic> get today => _dynamicMap(rawPayload['today']);
  Map<String, dynamic> get documentation =>
      _dynamicMap(rawPayload['documentation']);
  Map<String, dynamic> get diagnostics =>
      _dynamicMap(rawPayload['diagnostics']);
  List<Map<String, dynamic>> get recentActivity =>
      _mapList(rawPayload['recent_activity']);

  List<OpsSafetyCheck> get safetyChecks {
    final legacy = _mapList(rawPayload['safety_checks']);
    if (legacy.isNotEmpty) return legacy.map(OpsSafetyCheck.fromJson).toList();
    return checklist.map(OpsSafetyCheck.fromChecklist).toList();
  }

  List<String> get blockingIssues => blockingReasons;
  List<String> get recommendedActions => nextSafeActions;

  bool get dryRun =>
      _boolValue(summary.raw['dry_run']) ??
      _boolValue(runtime['dry_run']) ??
      _boolValue(_detailsRuntime()['dry_run']) ??
      true;
  bool get killSwitch =>
      _boolValue(summary.raw['kill_switch']) ??
      _boolValue(runtime['kill_switch']) ??
      _boolValue(_detailsRuntime()['kill_switch']) ??
      false;
  bool get kisRealOrderEnabled =>
      _boolValue(summary.raw['kis_real_order_enabled']) ??
      _boolValue(kis['kis_real_order_enabled']) ??
      _boolValue(_detailsRuntimeAppFlags()['kis_real_order_enabled']) ??
      false;
  bool get schedulerRealOrdersEnabled =>
      _boolValue(scheduler['scheduler_real_orders_allowed']) ??
      summary.schedulerRealOrdersAllowed;
  bool get schedulerSellEnabled =>
      _boolValue(summary.raw['kis_scheduler_sell_enabled']) ??
      _boolValue(scheduler['scheduler_sell_enabled']) ??
      false;
  bool get schedulerBuyEnabled =>
      _boolValue(summary.raw['kis_scheduler_buy_enabled']) ??
      _boolValue(scheduler['scheduler_buy_enabled']) ??
      false;
  bool get liveAutoSellEnabled =>
      _boolValue(summary.raw['kis_live_auto_sell_enabled']) ?? false;
  bool get liveAutoBuyEnabled =>
      _boolValue(summary.raw['kis_live_auto_buy_enabled']) ?? false;
  int get todayBrokerSubmits => _intValue(today['broker_submits']);
  int get todayOrderCount => _intValue(today['order_logs_created']);
  int get criticalIssueCount => summary.criticalBlockCount;
  int get warningCount => summary.warningCount;
  int get totalRunsToday => _intValue(today['total_runs']);
  int get blockedCountToday => _intValue(today['blocked_count']);
  int get failedCountToday => _intValue(today['failed_count']);

  int get activeAlertCount => summary.activeAlertCount;
  int get syncRequiredAlertCount => summary.syncRequiredAlertCount;

  String get topBlockReason {
    final reasons = today['top_block_reasons'];
    if (reasons is List && reasons.isNotEmpty && reasons.first is Map) {
      final first = Map<String, dynamic>.from(reasons.first as Map);
      final reason = first['reason']?.toString().trim();
      if (reason != null && reason.isNotEmpty) return reason;
    }
    return blockingReasons.isNotEmpty ? blockingReasons.first : 'n/a';
  }

  OpsReadinessChecklistItem? checklistItem(String key) {
    for (final item in checklist) {
      if (item.key == key) return item;
    }
    return null;
  }

  OpsSafetyCheck? check(String key) {
    for (final item in safetyChecks) {
      if (item.key == key) return item;
    }
    return null;
  }

  Map<String, List<OpsReadinessChecklistItem>> get groupedChecklist {
    final groups = <String, List<OpsReadinessChecklistItem>>{};
    for (final item in checklist) {
      groups.putIfAbsent(item.category, () => <OpsReadinessChecklistItem>[]);
      groups[item.category]!.add(item);
    }
    return groups;
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

  Map<String, dynamic> _detailsRuntime() {
    final runtimeDetails = details['runtime'];
    return runtimeDetails is Map
        ? Map<String, dynamic>.from(runtimeDetails)
        : const {};
  }

  Map<String, dynamic> _detailsRuntimeAppFlags() {
    final appFlags = _detailsRuntime()['app_flags'];
    return appFlags is Map ? Map<String, dynamic>.from(appFlags) : const {};
  }
}

class OpsProductionReadinessSummary {
  const OpsProductionReadinessSummary({
    required this.readyCount,
    required this.warningCount,
    required this.blockedCount,
    required this.unknownCount,
    required this.criticalBlockCount,
    required this.canUseGuardedLiveBuy,
    required this.canUseGuardedLiveSell,
    required this.canEnableSchedulerLiveOrders,
    required this.schedulerRealOrdersAllowed,
    required this.automationUnlockAllowed,
    required this.activeAlertCount,
    required this.criticalAlertCount,
    required this.warningAlertCount,
    required this.syncRequiredAlertCount,
    required this.raw,
  });

  factory OpsProductionReadinessSummary.fromJson(Map<String, dynamic> json) {
    return OpsProductionReadinessSummary(
      readyCount: _intValue(json['ready_count']),
      warningCount: _intValue(json['warning_count']),
      blockedCount:
          _intValue(json['blocked_count'] ?? json['critical_issue_count']),
      unknownCount: _intValue(json['unknown_count']),
      criticalBlockCount: _intValue(
          json['critical_block_count'] ?? json['critical_issue_count']),
      canUseGuardedLiveBuy:
          _boolValue(json['can_use_guarded_live_buy']) ?? false,
      canUseGuardedLiveSell:
          _boolValue(json['can_use_guarded_live_sell']) ?? false,
      canEnableSchedulerLiveOrders:
          _boolValue(json['can_enable_scheduler_live_orders']) ?? false,
      schedulerRealOrdersAllowed: _boolValue(
              json['scheduler_real_orders_allowed'] ??
                  json['kis_scheduler_allow_real_orders']) ??
          false,
      automationUnlockAllowed:
          _boolValue(json['automation_unlock_allowed']) ?? false,
      activeAlertCount: _intValue(json['active_alert_count']),
      criticalAlertCount: _intValue(json['critical_alert_count']),
      warningAlertCount: _intValue(json['warning_alert_count']),
      syncRequiredAlertCount: _intValue(json['sync_required_alert_count']),
      raw: json,
    );
  }

  final int readyCount;
  final int warningCount;
  final int blockedCount;
  final int unknownCount;
  final int criticalBlockCount;
  final bool canUseGuardedLiveBuy;
  final bool canUseGuardedLiveSell;
  final bool canEnableSchedulerLiveOrders;
  final bool schedulerRealOrdersAllowed;
  final bool automationUnlockAllowed;
  final int activeAlertCount;
  final int criticalAlertCount;
  final int warningAlertCount;
  final int syncRequiredAlertCount;
  final Map<String, dynamic> raw;
}

class OpsReadinessChecklistItem {
  const OpsReadinessChecklistItem({
    required this.key,
    required this.category,
    required this.status,
    required this.title,
    required this.detail,
    required this.blocking,
    required this.severity,
    required this.relatedType,
    required this.relatedId,
    required this.nextSafeAction,
  });

  factory OpsReadinessChecklistItem.fromJson(Map<String, dynamic> json) {
    return OpsReadinessChecklistItem(
      key: _stringValue(json['key'], fallback: ''),
      category: _stringValue(json['category'], fallback: 'runtime'),
      status: _normalizeCheckStatus(json['status']),
      title: _stringValue(json['title'], fallback: ''),
      detail: _stringValue(json['detail'], fallback: ''),
      blocking: _boolValue(json['blocking']) ?? false,
      severity: _stringValue(json['severity'], fallback: 'info'),
      relatedType: _nullableString(json['related_type']),
      relatedId: _nullableString(json['related_id']),
      nextSafeAction: _stringValue(json['next_safe_action'], fallback: ''),
    );
  }

  factory OpsReadinessChecklistItem.fromLegacyJson(Map<String, dynamic> json) {
    final legacyStatus = _stringValue(json['status'], fallback: 'INFO');
    return OpsReadinessChecklistItem(
      key: _stringValue(json['key'], fallback: ''),
      category: _stringValue(json['category'], fallback: 'runtime'),
      status: _legacyStatusToCanonical(legacyStatus),
      title: _stringValue(json['label'], fallback: ''),
      detail: _stringValue(json['message'], fallback: ''),
      blocking: legacyStatus.toUpperCase() == 'FAIL',
      severity: legacyStatus.toUpperCase() == 'FAIL' ? 'critical' : 'warning',
      relatedType: null,
      relatedId: null,
      nextSafeAction: _stringValue(json['recommended_action'], fallback: ''),
    );
  }

  final String key;
  final String category;
  final String status;
  final String title;
  final String detail;
  final bool blocking;
  final String severity;
  final String? relatedType;
  final String? relatedId;
  final String nextSafeAction;
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

  factory OpsSafetyCheck.fromChecklist(OpsReadinessChecklistItem item) {
    return OpsSafetyCheck(
      key: item.key,
      label: item.title,
      status: _canonicalStatusToLegacy(item.status),
      value: item.status,
      message: item.detail,
      recommendedAction: item.nextSafeAction,
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

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

DateTime? _dateTimeValue(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return DateTime.tryParse(text);
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

String _normalizeOverallStatus(Object? value) {
  final normalized = value?.toString().trim().toLowerCase() ?? '';
  if (normalized == 'ready' || normalized == 'live_ready') return 'ready';
  if (normalized == 'warning' || normalized == 'review_required') {
    return 'warning';
  }
  if (normalized == 'blocked' || normalized == 'safe_dry_run') {
    return 'blocked';
  }
  if (normalized == 'unknown') return 'unknown';
  return 'unknown';
}

String _normalizeCheckStatus(Object? value) {
  final normalized = value?.toString().trim().toLowerCase() ?? '';
  if (normalized == 'pass' || normalized == 'passed') return 'pass';
  if (normalized == 'warn' || normalized == 'warning') return 'warn';
  if (normalized == 'fail' || normalized == 'failed') return 'fail';
  return 'unknown';
}

String _legacyStatusToCanonical(String value) {
  switch (value.trim().toUpperCase()) {
    case 'PASS':
      return 'pass';
    case 'WARN':
      return 'warn';
    case 'FAIL':
      return 'fail';
    default:
      return 'unknown';
  }
}

String _canonicalStatusToLegacy(String value) {
  switch (value.trim().toLowerCase()) {
    case 'pass':
      return 'PASS';
    case 'warn':
      return 'WARN';
    case 'fail':
      return 'FAIL';
    default:
      return 'INFO';
  }
}
