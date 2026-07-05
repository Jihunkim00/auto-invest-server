class OperatorAlerts {
  const OperatorAlerts({
    this.generatedAt,
    required this.timezone,
    required this.provider,
    required this.market,
    required this.summary,
    required this.alerts,
    required this.nextSafeActions,
    required this.safetyFlags,
  });

  factory OperatorAlerts.fromJson(Map<String, dynamic> json) {
    return OperatorAlerts(
      generatedAt: _dateTime(json['generated_at']),
      timezone: _string(json['timezone'], 'Asia/Seoul'),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      summary: OperatorAlertsSummary.fromJson(_map(json['summary'])),
      alerts: _maps(json['alerts'])
          .map(OperatorAlert.fromJson)
          .toList(growable: false),
      nextSafeActions: _strings(json['next_safe_actions']),
      safetyFlags: _map(json['safety_flags']),
    );
  }

  final DateTime? generatedAt;
  final String timezone;
  final String provider;
  final String market;
  final OperatorAlertsSummary summary;
  final List<OperatorAlert> alerts;
  final List<String> nextSafeActions;
  final Map<String, dynamic> safetyFlags;

  bool get isEmpty => alerts.isEmpty;
  bool get isReadOnly => _bool(safetyFlags['read_only'], fallback: true);
}

class OperatorAlertsSummary {
  const OperatorAlertsSummary({
    required this.activeAlertCount,
    required this.criticalCount,
    required this.warningCount,
    required this.infoCount,
    required this.syncRequiredCount,
    required this.rejectedOrderCount,
    required this.blockedAttemptCount,
    required this.stalePromotionCount,
    required this.incompletePlCount,
    required this.runtimeWarningCount,
  });

  factory OperatorAlertsSummary.fromJson(Map<String, dynamic> json) {
    return OperatorAlertsSummary(
      activeAlertCount: _int(json['active_alert_count']),
      criticalCount: _int(json['critical_count']),
      warningCount: _int(json['warning_count']),
      infoCount: _int(json['info_count']),
      syncRequiredCount: _int(json['sync_required_count']),
      rejectedOrderCount: _int(json['rejected_order_count']),
      blockedAttemptCount: _int(json['blocked_attempt_count']),
      stalePromotionCount: _int(json['stale_promotion_count']),
      incompletePlCount: _int(json['incomplete_pl_count']),
      runtimeWarningCount: _int(json['runtime_warning_count']),
    );
  }

  final int activeAlertCount;
  final int criticalCount;
  final int warningCount;
  final int infoCount;
  final int syncRequiredCount;
  final int rejectedOrderCount;
  final int blockedAttemptCount;
  final int stalePromotionCount;
  final int incompletePlCount;
  final int runtimeWarningCount;
}

class OperatorAlert {
  const OperatorAlert({
    required this.alertId,
    required this.severity,
    required this.category,
    required this.status,
    required this.title,
    required this.message,
    required this.provider,
    required this.market,
    this.symbol,
    required this.relatedType,
    this.relatedId,
    this.createdAt,
    this.updatedAt,
    required this.source,
    required this.reasonCode,
    required this.riskFlags,
    required this.gatingNotes,
    required this.nextSafeAction,
    required this.isActionable,
    required this.actionType,
  });

  factory OperatorAlert.fromJson(Map<String, dynamic> json) {
    return OperatorAlert(
      alertId: _string(json['alert_id'], ''),
      severity: _string(json['severity'], 'info'),
      category: _string(json['category'], 'system'),
      status: _string(json['status'], 'active'),
      title: _string(json['title'], ''),
      message: _string(json['message'], ''),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      symbol: _nullableString(json['symbol']),
      relatedType: _string(json['related_type'], 'system'),
      relatedId: _nullableString(json['related_id']),
      createdAt: _dateTime(json['created_at']),
      updatedAt: _dateTime(json['updated_at']),
      source: _string(json['source'], 'operator_alerts'),
      reasonCode: _string(json['reason_code'], 'unknown'),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      nextSafeAction: _string(json['next_safe_action'], ''),
      isActionable: _bool(json['is_actionable'], fallback: false),
      actionType: _string(json['action_type'], 'none'),
    );
  }

  final String alertId;
  final String severity;
  final String category;
  final String status;
  final String title;
  final String message;
  final String provider;
  final String market;
  final String? symbol;
  final String relatedType;
  final String? relatedId;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final String source;
  final String reasonCode;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final String nextSafeAction;
  final bool isActionable;
  final String actionType;

  bool get isCritical => severity.toLowerCase() == 'critical';
  bool get isWarning => severity.toLowerCase() == 'warning';
}

String _string(Object? value, String fallback) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? fallback : text;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty || text == 'null' ? null : text;
}

int _int(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString().trim() ?? '') ?? 0;
}

bool _bool(Object? value, {bool fallback = false}) {
  if (value is bool) return value;
  final text = value?.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return fallback;
}

Map<String, dynamic> _map(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return const <String, dynamic>{};
}

List<Map<String, dynamic>> _maps(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map) Map<String, dynamic>.from(item),
  ];
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item != null && item.toString().trim().isNotEmpty)
        item.toString().trim(),
  ];
}

DateTime? _dateTime(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return null;
  return DateTime.tryParse(text);
}
