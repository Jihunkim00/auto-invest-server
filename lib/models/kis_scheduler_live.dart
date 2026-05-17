class KisSchedulerLiveResult {
  const KisSchedulerLiveResult({
    required this.status,
    required this.mode,
    required this.result,
    required this.action,
    required this.reason,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.schedulerRealOrderEnabled,
    required this.checks,
    required this.safety,
    required this.sellResult,
    required this.buyResult,
    this.orderId,
    this.createdAt,
  });

  factory KisSchedulerLiveResult.fromJson(Map<String, dynamic> json) {
    final safety = _dynamicMap(json['safety']);
    return KisSchedulerLiveResult(
      status: _stringValue(json['status'], fallback: 'ok'),
      mode: _stringValue(json['mode'], fallback: 'kis_scheduler_live_once'),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      reason: _stringValue(json['reason'], fallback: ''),
      orderId: _nullableInt(json['order_id']),
      realOrderSubmitted: _boolValue(
              json['real_order_submitted'] ?? safety['real_order_submitted']) ??
          false,
      brokerSubmitCalled: _boolValue(
              json['broker_submit_called'] ?? safety['broker_submit_called']) ??
          false,
      manualSubmitCalled: _boolValue(
              json['manual_submit_called'] ?? safety['manual_submit_called']) ??
          false,
      schedulerRealOrderEnabled: _boolValue(
              json['scheduler_real_order_enabled'] ??
                  safety['scheduler_real_order_enabled']) ??
          false,
      checks: _dynamicMap(json['checks']),
      safety: safety,
      sellResult: _dynamicMap(json['sell_result']),
      buyResult: _dynamicMap(json['buy_result']),
      createdAt: _nullableString(json['created_at']),
    );
  }

  final String status;
  final String mode;
  final String result;
  final String action;
  final String reason;
  final int? orderId;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool schedulerRealOrderEnabled;
  final Map<String, dynamic> checks;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> sellResult;
  final Map<String, dynamic> buyResult;
  final String? createdAt;

  bool get submitted => realOrderSubmitted || result == 'submitted';

  bool check(String key) => _boolValue(checks[key]) ?? false;

  bool? nullableCheck(String key) => _boolValue(checks[key]);

  int? safetyInt(String key) => _nullableInt(safety[key]);
}

Map<String, dynamic> _dynamicMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
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

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim();
  if (text.isEmpty || text == 'null') return null;
  return int.tryParse(text);
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
