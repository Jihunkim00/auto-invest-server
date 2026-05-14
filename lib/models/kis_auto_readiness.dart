class KisAutoReadiness {
  const KisAutoReadiness({
    required this.autoOrderReady,
    required this.liveAutoEnabled,
    required this.realOrderSubmitAllowed,
    required this.reason,
    required this.checks,
    required this.safety,
    this.futureAutoOrderReady = false,
    this.preflight = false,
    this.checkedAt,
    this.createdAt,
    this.blockedBy = const [],
  });

  factory KisAutoReadiness.fromJson(Map<String, dynamic> json) {
    return KisAutoReadiness(
      autoOrderReady: _boolValue(json['auto_order_ready']) ?? false,
      futureAutoOrderReady:
          _boolValue(json['future_auto_order_ready']) ?? false,
      liveAutoEnabled: _boolValue(json['live_auto_enabled']) ?? false,
      realOrderSubmitAllowed:
          _boolValue(json['real_order_submit_allowed']) ?? false,
      reason: _stringValue(json['reason'], fallback: ''),
      checks: _boolMap(json['checks']),
      safety: _boolMap(json['safety']),
      preflight: _boolValue(json['preflight']) ?? false,
      checkedAt: _nullableString(json['checked_at']),
      createdAt: _nullableString(json['created_at']),
      blockedBy: _stringList(json['blocked_by']),
    );
  }

  factory KisAutoReadiness.safeDefault() {
    return const KisAutoReadiness(
      autoOrderReady: false,
      futureAutoOrderReady: false,
      liveAutoEnabled: false,
      realOrderSubmitAllowed: false,
      reason: 'live_auto_disabled_by_default',
      checks: {
        'dry_run': true,
        'kill_switch': false,
        'kis_scheduler_allow_real_orders': false,
        'live_auto_buy_enabled': false,
        'live_auto_sell_enabled': false,
      },
      safety: {
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'scheduler_real_order_enabled': false,
        'requires_manual_confirm': true,
      },
      blockedBy: [
        'live_auto_disabled_by_default',
        'buy_auto_disabled',
        'sell_auto_disabled',
      ],
    );
  }

  final bool autoOrderReady;
  final bool futureAutoOrderReady;
  final bool liveAutoEnabled;
  final bool realOrderSubmitAllowed;
  final String reason;
  final Map<String, bool> checks;
  final Map<String, bool> safety;
  final bool preflight;
  final String? checkedAt;
  final String? createdAt;
  final List<String> blockedBy;

  bool check(String key) => checks[key] ?? false;
  bool safetyFlag(String key) => safety[key] ?? false;
}

Map<String, bool> _boolMap(Object? value) {
  if (value is! Map) return const {};
  return Map<String, bool>.fromEntries(
    value.entries.map(
      (entry) => MapEntry(
        entry.key.toString(),
        _boolValue(entry.value) ?? false,
      ),
    ),
  );
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
