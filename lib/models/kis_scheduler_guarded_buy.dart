class KisSchedulerGuardedBuyResult {
  const KisSchedulerGuardedBuyResult({
    required this.status,
    required this.provider,
    required this.market,
    required this.mode,
    required this.triggerSource,
    required this.requestedTriggerSource,
    required this.slotLabel,
    required this.result,
    required this.action,
    required this.reason,
    required this.buyOnly,
    required this.schedulerBuyOnly,
    required this.sellPriorityRequired,
    required this.sellPriorityChecked,
    required this.sellReadyBlocksBuy,
    required this.schedulerBuyEnabled,
    required this.schedulerRealOrdersEnabled,
    required this.realOrderSubmitAllowed,
    required this.buyExecutionAllowed,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.summary,
    required this.sellReviewResult,
    required this.buyResult,
    required this.blockReasons,
    required this.checks,
    required this.safety,
    required this.diagnostics,
    required this.dailyLimit,
    required this.duplicateOrderCheck,
    required this.marketSessionCheck,
    required this.rawPayload,
    this.primaryBlockReason,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    this.symbol,
    this.companyName,
    this.quantity,
    this.estimatedNotional,
    this.createdAt,
  });

  factory KisSchedulerGuardedBuyResult.fromJson(Map<String, dynamic> json) {
    final safety = _dynamicMap(json['safety']);
    final summary = _dynamicMap(json['summary']);
    return KisSchedulerGuardedBuyResult(
      status: _stringValue(json['status'], fallback: 'ok'),
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(json['mode'], fallback: 'kis_scheduler_guarded_buy'),
      triggerSource: _stringValue(json['trigger_source'],
          fallback: 'scheduler_guarded_buy'),
      requestedTriggerSource: _stringValue(
        json['requested_trigger_source'],
        fallback: 'scheduler_manual_test',
      ),
      slotLabel:
          _stringValue(json['slot_label'], fallback: 'manual_guarded_buy'),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      reason: _stringValue(json['reason'], fallback: ''),
      primaryBlockReason: _nullableString(
        json['primary_block_reason'] ?? summary['primary_block_reason'],
      ),
      buyOnly: _boolValue(json['buy_only'] ?? safety['buy_only']) ?? true,
      schedulerBuyOnly: _boolValue(
              json['scheduler_buy_only'] ?? safety['scheduler_buy_only']) ??
          true,
      sellPriorityRequired: _boolValue(json['sell_priority_required'] ??
              safety['sell_priority_required']) ??
          true,
      sellPriorityChecked: _boolValue(json['sell_priority_checked'] ??
              safety['sell_review_completed']) ??
          false,
      sellReadyBlocksBuy: _boolValue(json['sell_ready_blocks_buy'] ??
              safety['sell_ready_blocks_buy']) ??
          true,
      schedulerBuyEnabled: _boolValue(json['scheduler_buy_enabled'] ??
              safety['kis_scheduler_buy_enabled']) ??
          false,
      schedulerRealOrdersEnabled: _boolValue(
            json['scheduler_real_orders_enabled'] ??
                safety['scheduler_real_orders_enabled'],
          ) ??
          false,
      realOrderSubmitAllowed:
          _boolValue(json['real_order_submit_allowed']) ?? false,
      buyExecutionAllowed: _boolValue(json['buy_execution_allowed']) ?? false,
      realOrderSubmitted: _boolValue(
            json['real_order_submitted'] ?? safety['real_order_submitted'],
          ) ??
          false,
      brokerSubmitCalled: _boolValue(
            json['broker_submit_called'] ?? safety['broker_submit_called'],
          ) ??
          false,
      manualSubmitCalled: _boolValue(
            json['manual_submit_called'] ?? safety['manual_submit_called'],
          ) ??
          false,
      orderId: _nullableInt(json['order_id'] ?? json['order_log_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      symbol: _nullableString(json['symbol'] ?? summary['symbol']),
      companyName:
          _nullableString(json['company_name'] ?? summary['company_name']),
      quantity: _nullableInt(json['quantity'] ?? summary['quantity']),
      estimatedNotional: _nullableDouble(
          json['estimated_notional'] ?? summary['estimated_notional']),
      summary: summary,
      sellReviewResult: _dynamicMap(json['sell_review_result']),
      buyResult: _dynamicMap(json['buy_result']),
      blockReasons: _stringList(json['block_reasons'] ?? json['blocked_by']),
      checks: _dynamicMap(json['checks']),
      safety: safety,
      diagnostics: _dynamicMap(json['diagnostics']),
      dailyLimit: _dynamicMap(json['daily_limit']),
      duplicateOrderCheck: _dynamicMap(json['duplicate_order_check']),
      marketSessionCheck: _dynamicMap(json['market_session_check']),
      rawPayload: _dynamicMap(json),
      createdAt: _nullableString(json['created_at']),
    );
  }

  final String status;
  final String provider;
  final String market;
  final String mode;
  final String triggerSource;
  final String requestedTriggerSource;
  final String slotLabel;
  final String result;
  final String action;
  final String reason;
  final String? primaryBlockReason;
  final bool buyOnly;
  final bool schedulerBuyOnly;
  final bool sellPriorityRequired;
  final bool sellPriorityChecked;
  final bool sellReadyBlocksBuy;
  final bool schedulerBuyEnabled;
  final bool schedulerRealOrdersEnabled;
  final bool realOrderSubmitAllowed;
  final bool buyExecutionAllowed;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final String? symbol;
  final String? companyName;
  final int? quantity;
  final double? estimatedNotional;
  final Map<String, dynamic> summary;
  final Map<String, dynamic> sellReviewResult;
  final Map<String, dynamic> buyResult;
  final List<String> blockReasons;
  final Map<String, dynamic> checks;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> diagnostics;
  final Map<String, dynamic> dailyLimit;
  final Map<String, dynamic> duplicateOrderCheck;
  final Map<String, dynamic> marketSessionCheck;
  final Map<String, dynamic> rawPayload;
  final String? createdAt;

  bool get submitted => realOrderSubmitted || result == 'submitted';

  bool get sellSkippedBuy =>
      primaryBlockReason == 'sell_review_required_before_buy' ||
      buyResult['buy_execution_skipped'] == true;

  bool check(String key) => _boolValue(checks[key]) ?? false;

  bool? nullableCheck(String key) => _boolValue(checks[key]);

  bool safetyFlag(String key) => _boolValue(safety[key]) ?? false;

  bool? nullableSafety(String key) => _boolValue(safety[key]);

  int? safetyInt(String key) => _nullableInt(safety[key]);

  int? dailyLimitInt(String key) => _nullableInt(dailyLimit[key]);
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
