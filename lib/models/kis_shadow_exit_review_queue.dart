class KisShadowExitReviewQueue {
  const KisShadowExitReviewQueue({
    required this.status,
    required this.mode,
    required this.reviewWindowDays,
    required this.summary,
    required this.items,
    required this.safety,
    this.createdAt,
  });

  factory KisShadowExitReviewQueue.fromJson(Map<String, dynamic> json) {
    return KisShadowExitReviewQueue(
      status: _stringValue(json['status'], fallback: 'ok'),
      mode: _stringValue(json['mode'], fallback: 'shadow_exit_review_queue'),
      reviewWindowDays: _intValue(json['review_window_days'], fallback: 30),
      summary: KisShadowExitReviewQueueSummary.fromJson(json['summary']),
      items: _itemList(json['items']),
      safety: KisShadowExitReviewQueueSafety.fromJson(json['safety']),
      createdAt: _nullableString(json['created_at']),
    );
  }

  final String status;
  final String mode;
  final int reviewWindowDays;
  final KisShadowExitReviewQueueSummary summary;
  final List<KisShadowExitReviewQueueItem> items;
  final KisShadowExitReviewQueueSafety safety;
  final String? createdAt;
}

class KisShadowExitReviewQueueSummary {
  const KisShadowExitReviewQueueSummary({
    required this.openCount,
    required this.reviewedCount,
    required this.dismissedCount,
    required this.wouldSellOpenCount,
    required this.manualReviewOpenCount,
    required this.repeatedSymbolCount,
    this.latestOpenAt,
  });

  factory KisShadowExitReviewQueueSummary.fromJson(Object? value) {
    final json = _mapValue(value);
    return KisShadowExitReviewQueueSummary(
      openCount: _intValue(json['open_count']),
      reviewedCount: _intValue(json['reviewed_count']),
      dismissedCount: _intValue(json['dismissed_count']),
      wouldSellOpenCount: _intValue(json['would_sell_open_count']),
      manualReviewOpenCount: _intValue(json['manual_review_open_count']),
      repeatedSymbolCount: _intValue(json['repeated_symbol_count']),
      latestOpenAt: _nullableString(json['latest_open_at']),
    );
  }

  final int openCount;
  final int reviewedCount;
  final int dismissedCount;
  final int wouldSellOpenCount;
  final int manualReviewOpenCount;
  final int repeatedSymbolCount;
  final String? latestOpenAt;
}

class KisShadowExitReviewQueueItem {
  const KisShadowExitReviewQueueItem({
    required this.queueId,
    required this.symbol,
    required this.decision,
    required this.action,
    required this.trigger,
    required this.triggerSource,
    required this.severity,
    required this.occurrenceCount,
    required this.status,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.firstSeenAt,
    this.latestSeenAt,
    this.latestUnrealizedPl,
    this.latestUnrealizedPlPct,
    this.latestCostBasis,
    this.latestCurrentValue,
    this.latestCurrentPrice,
    this.suggestedQuantity,
    this.reason = '',
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.sourceRunId,
    this.sourceRunKey,
    this.sourceSignalId,
    this.linkedManualOrderId,
    this.linkedManualOrderStatus,
    this.linkedManualOrderCreatedAt,
    this.linkedManualOrderFilledQuantity,
    this.linkedManualOrderAverageFillPrice,
    this.reviewedAt,
    this.dismissedAt,
    this.operatorNote,
  });

  factory KisShadowExitReviewQueueItem.fromJson(Map<String, dynamic> json) {
    return KisShadowExitReviewQueueItem(
      queueId: _stringValue(json['queue_id'], fallback: ''),
      symbol: _stringValue(json['symbol'], fallback: 'UNKNOWN'),
      decision: _stringValue(json['decision'], fallback: 'hold'),
      action: _stringValue(json['action'], fallback: 'hold'),
      trigger: _stringValue(json['trigger'], fallback: 'unknown'),
      triggerSource: _stringValue(json['trigger_source'], fallback: 'unknown'),
      severity: _stringValue(json['severity'], fallback: 'review'),
      occurrenceCount: _intValue(json['occurrence_count']),
      firstSeenAt: _nullableString(json['first_seen_at']),
      latestSeenAt: _nullableString(json['latest_seen_at']),
      latestUnrealizedPl: _nullableDouble(json['latest_unrealized_pl']),
      latestUnrealizedPlPct: _nullableDouble(json['latest_unrealized_pl_pct']),
      latestCostBasis: _nullableDouble(json['latest_cost_basis']),
      latestCurrentValue: _nullableDouble(json['latest_current_value']),
      latestCurrentPrice: _nullableDouble(json['latest_current_price']),
      suggestedQuantity: _nullableDouble(json['suggested_quantity']),
      reason: _stringValue(json['reason'], fallback: ''),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      sourceRunId: _nullableInt(json['source_run_id']),
      sourceRunKey: _nullableString(json['source_run_key']),
      sourceSignalId: _nullableInt(json['source_signal_id']),
      linkedManualOrderId: _nullableInt(json['linked_manual_order_id']),
      linkedManualOrderStatus:
          _nullableString(json['linked_manual_order_status']),
      linkedManualOrderCreatedAt:
          _nullableString(json['linked_manual_order_created_at']),
      linkedManualOrderFilledQuantity:
          _nullableDouble(json['linked_manual_order_filled_quantity']),
      linkedManualOrderAverageFillPrice:
          _nullableDouble(json['linked_manual_order_average_fill_price']),
      status: _stringValue(json['status'], fallback: 'open'),
      reviewedAt: _nullableString(json['reviewed_at']),
      dismissedAt: _nullableString(json['dismissed_at']),
      operatorNote: _nullableString(json['operator_note']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
    );
  }

  final String queueId;
  final String symbol;
  final String decision;
  final String action;
  final String trigger;
  final String triggerSource;
  final String severity;
  final int occurrenceCount;
  final String? firstSeenAt;
  final String? latestSeenAt;
  final double? latestUnrealizedPl;
  final double? latestUnrealizedPlPct;
  final double? latestCostBasis;
  final double? latestCurrentValue;
  final double? latestCurrentPrice;
  final double? suggestedQuantity;
  final String reason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final int? sourceRunId;
  final String? sourceRunKey;
  final int? sourceSignalId;
  final int? linkedManualOrderId;
  final String? linkedManualOrderStatus;
  final String? linkedManualOrderCreatedAt;
  final double? linkedManualOrderFilledQuantity;
  final double? linkedManualOrderAverageFillPrice;
  final String status;
  final String? reviewedAt;
  final String? dismissedAt;
  final String? operatorNote;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;

  bool get isOpen => status.trim().toLowerCase() == 'open';
  bool get isReviewed => status.trim().toLowerCase() == 'reviewed';
  bool get isDismissed => status.trim().toLowerCase() == 'dismissed';
}

class KisShadowExitReviewQueueSafety {
  const KisShadowExitReviewQueueSafety({
    required this.readOnly,
    required this.operatorStateOnly,
    required this.createsOrders,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.autoBuyEnabled,
    required this.autoSellEnabled,
    required this.schedulerRealOrderEnabled,
  });

  factory KisShadowExitReviewQueueSafety.fromJson(Object? value) {
    final json = _mapValue(value);
    return KisShadowExitReviewQueueSafety(
      readOnly: _boolValue(json['read_only']) ?? true,
      operatorStateOnly: _boolValue(json['operator_state_only']) ?? true,
      createsOrders: _boolValue(json['creates_orders']) ?? false,
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      autoBuyEnabled: _boolValue(json['auto_buy_enabled']) ?? false,
      autoSellEnabled: _boolValue(json['auto_sell_enabled']) ?? false,
      schedulerRealOrderEnabled:
          _boolValue(json['scheduler_real_order_enabled']) ?? false,
    );
  }

  final bool readOnly;
  final bool operatorStateOnly;
  final bool createsOrders;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool autoBuyEnabled;
  final bool autoSellEnabled;
  final bool schedulerRealOrderEnabled;
}

class KisShadowExitReviewQueueAction {
  const KisShadowExitReviewQueueAction({
    required this.status,
    required this.mode,
    required this.action,
    required this.item,
    required this.safety,
    this.createdAt,
  });

  factory KisShadowExitReviewQueueAction.fromJson(Map<String, dynamic> json) {
    return KisShadowExitReviewQueueAction(
      status: _stringValue(json['status'], fallback: 'ok'),
      mode: _stringValue(json['mode'], fallback: 'shadow_exit_review_queue'),
      action: _stringValue(json['action'], fallback: ''),
      item: KisShadowExitReviewQueueStateItem.fromJson(json['item']),
      safety: KisShadowExitReviewQueueSafety.fromJson(json['safety']),
      createdAt: _nullableString(json['created_at']),
    );
  }

  final String status;
  final String mode;
  final String action;
  final KisShadowExitReviewQueueStateItem item;
  final KisShadowExitReviewQueueSafety safety;
  final String? createdAt;
}

class KisShadowExitReviewQueueStateItem {
  const KisShadowExitReviewQueueStateItem({
    required this.queueId,
    required this.symbol,
    required this.trigger,
    required this.status,
    this.operatorNote,
    this.reviewedAt,
    this.dismissedAt,
  });

  factory KisShadowExitReviewQueueStateItem.fromJson(Object? value) {
    final json = _mapValue(value);
    return KisShadowExitReviewQueueStateItem(
      queueId: _stringValue(json['queue_id'], fallback: ''),
      symbol: _stringValue(json['symbol'], fallback: 'UNKNOWN'),
      trigger: _stringValue(json['trigger'], fallback: 'unknown'),
      status: _stringValue(json['status'], fallback: 'open'),
      operatorNote: _nullableString(json['operator_note']),
      reviewedAt: _nullableString(json['reviewed_at']),
      dismissedAt: _nullableString(json['dismissed_at']),
    );
  }

  final String queueId;
  final String symbol;
  final String trigger;
  final String status;
  final String? operatorNote;
  final String? reviewedAt;
  final String? dismissedAt;
}

List<KisShadowExitReviewQueueItem> _itemList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisShadowExitReviewQueueItem.fromJson(
          Map<String, dynamic>.from(item)))
      .toList();
}

Map<String, dynamic> _mapValue(Object? value) {
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

int _intValue(Object? value, {int fallback = 0}) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString().trim() ?? '') ?? fallback;
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
