class KisLimitedAutoSell {
  const KisLimitedAutoSell({
    required this.status,
    required this.mode,
    required this.result,
    required this.action,
    required this.reason,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.autoBuyEnabled,
    required this.autoSellEnabled,
    required this.schedulerRealOrderEnabled,
    required this.checks,
    required this.safety,
    required this.auditMetadata,
    this.symbol,
    this.quantity,
    this.trigger,
    this.triggerSource,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    this.createdAt,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.costBasis,
    this.currentValue,
    this.currentPrice,
    this.notional,
    this.blockedBy = const [],
    this.failedChecks = const [],
  });

  factory KisLimitedAutoSell.fromJson(Map<String, dynamic> json) {
    return KisLimitedAutoSell(
      status: _stringValue(json['status'], fallback: 'ok'),
      mode: _stringValue(json['mode'], fallback: 'limited_auto_sell'),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      reason: _stringValue(json['reason'], fallback: ''),
      symbol: _nullableString(json['symbol']),
      quantity: _nullableInt(json['quantity'] ?? json['qty']),
      trigger: _nullableString(json['trigger'] ?? json['exit_trigger']),
      triggerSource: _nullableString(
          json['trigger_source'] ?? json['exit_trigger_source']),
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      autoBuyEnabled: _boolValue(json['auto_buy_enabled']) ?? false,
      autoSellEnabled: _boolValue(json['auto_sell_enabled']) ?? false,
      schedulerRealOrderEnabled:
          _boolValue(json['scheduler_real_order_enabled']) ?? false,
      checks: _dynamicMap(json['checks']),
      safety: _dynamicMap(json['safety']),
      auditMetadata: _dynamicMap(json['audit_metadata']),
      createdAt: _nullableString(json['created_at']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentValue: _nullableDouble(json['current_value']),
      currentPrice: _nullableDouble(json['current_price']),
      notional: _nullableDouble(json['notional']),
      blockedBy: _stringList(json['blocked_by']),
      failedChecks: _stringList(json['failed_checks']),
    );
  }

  final String status;
  final String mode;
  final String result;
  final String action;
  final String reason;
  final String? symbol;
  final int? quantity;
  final String? trigger;
  final String? triggerSource;
  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool autoBuyEnabled;
  final bool autoSellEnabled;
  final bool schedulerRealOrderEnabled;
  final Map<String, dynamic> checks;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> auditMetadata;
  final String? createdAt;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final double? costBasis;
  final double? currentValue;
  final double? currentPrice;
  final double? notional;
  final List<String> blockedBy;
  final List<String> failedChecks;

  bool get submitted => realOrderSubmitted || result == 'submitted';

  bool check(String key) => _boolValue(checks[key]) ?? false;

  bool? nullableCheck(String key) => _boolValue(checks[key]);

  bool safetyFlag(String key) => _boolValue(safety[key]) ?? false;

  int? safetyInt(String key) => _nullableInt(safety[key]);

  double? safetyDouble(String key) => _nullableDouble(safety[key]);
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

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
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
