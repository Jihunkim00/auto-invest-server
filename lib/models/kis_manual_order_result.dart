class KisManualOrderResult {
  const KisManualOrderResult({
    required this.orderId,
    required this.broker,
    required this.market,
    required this.symbol,
    required this.side,
    required this.orderType,
    required this.requestedQty,
    required this.filledQty,
    required this.remainingQty,
    required this.avgFillPrice,
    required this.kisOdno,
    required this.internalStatus,
    required this.brokerOrderStatus,
    required this.createdAt,
    required this.submittedAt,
    required this.filledAt,
    required this.canceledAt,
    required this.lastSyncedAt,
    required this.syncError,
    required this.displayStatus,
    required this.clearStatusLabel,
    required this.isSyncable,
    required this.isTerminal,
    this.sourceMetadata = const {},
    this.source,
    this.sourceType,
    this.exitTrigger,
    this.exitTriggerSource,
    this.rejectedReason,
    this.manualConfirmRequired,
    this.autoSellEnabled,
    this.schedulerRealOrderEnabled,
    this.realOrderSubmitAllowed,
  });

  final int orderId;
  final String broker;
  final String market;
  final String symbol;
  final String side;
  final String orderType;
  final double? requestedQty;
  final double filledQty;
  final double? remainingQty;
  final double? avgFillPrice;
  final String? kisOdno;
  final String internalStatus;
  final String? brokerOrderStatus;
  final String? createdAt;
  final String? submittedAt;
  final String? filledAt;
  final String? canceledAt;
  final String? lastSyncedAt;
  final String? syncError;
  final String displayStatus;
  final String clearStatusLabel;
  final bool isSyncable;
  final bool isTerminal;
  final Map<String, dynamic> sourceMetadata;
  final String? source;
  final String? sourceType;
  final String? exitTrigger;
  final String? exitTriggerSource;
  final String? rejectedReason;
  final bool? manualConfirmRequired;
  final bool? autoSellEnabled;
  final bool? schedulerRealOrderEnabled;
  final bool? realOrderSubmitAllowed;

  bool get hasSyncError => syncError != null && syncError!.isNotEmpty;
  bool get hasKisOdno => kisOdno != null && kisOdno!.trim().isNotEmpty;
  bool get isFromExitPreflight => source == 'kis_live_exit_preflight';
  bool get canCancel => hasKisOdno && isSyncable && !isTerminal;
  bool get isFilled => internalStatus.toUpperCase() == 'FILLED';
  bool get isPartial => internalStatus.toUpperCase() == 'PARTIALLY_FILLED';
  bool get isAccepted => internalStatus.toUpperCase() == 'ACCEPTED';
  bool get isUnknownStale => internalStatus.toUpperCase() == 'UNKNOWN_STALE';
  bool get isCanceled {
    final status = internalStatus.toUpperCase();
    return status == 'CANCELED' || status == 'CANCELLED';
  }

  bool get isRejected => clearStatusLabel == 'REJECTED';
  String? get validatedAt => isRejected ? null : createdAt;
  String? get rejectedAt => isRejected ? createdAt : null;

  factory KisManualOrderResult.fromJson(Map<String, dynamic> json) {
    final internalStatus = _readString(json['internal_status'], 'UNKNOWN');
    return KisManualOrderResult(
      orderId: _readInt(json['order_id'], 0),
      broker: _readString(json['broker'], 'kis'),
      market: _readString(json['market'], 'KR'),
      symbol: _readString(json['symbol'], ''),
      side: _readString(json['side'], ''),
      orderType: _readString(json['order_type'], 'market'),
      requestedQty: _readNullableDouble(json['requested_qty'] ?? json['qty']),
      filledQty: _readNullableDouble(json['filled_qty']) ?? 0,
      remainingQty: _readNullableDouble(json['remaining_qty']),
      avgFillPrice: _readNullableDouble(json['avg_fill_price']),
      kisOdno: _readNullableString(json['kis_odno'] ?? json['broker_order_id']),
      internalStatus: internalStatus,
      brokerOrderStatus: _readNullableString(
          json['broker_order_status'] ?? json['broker_status']),
      createdAt: _readNullableString(json['created_at']),
      submittedAt: _readNullableString(json['submitted_at']),
      filledAt: _readNullableString(json['filled_at']),
      canceledAt: _readNullableString(json['canceled_at']),
      lastSyncedAt: _readNullableString(json['last_synced_at']),
      syncError: _readNullableString(json['sync_error']),
      displayStatus: _readString(
          json['display_status'], clearKisStatusLabel(internalStatus)),
      clearStatusLabel: _readString(
          json['clear_status'], clearKisStatusLabel(internalStatus)),
      isSyncable:
          json['is_syncable'] == true || isSyncableKisStatus(internalStatus),
      isTerminal:
          json['is_terminal'] == true || isTerminalKisStatus(internalStatus),
      sourceMetadata:
          Map<String, dynamic>.from((json['source_metadata'] as Map?) ?? {}),
      source: _readNullableString(json['source']),
      sourceType: _readNullableString(json['source_type']),
      exitTrigger: _readNullableString(json['exit_trigger']),
      exitTriggerSource: _readNullableString(json['exit_trigger_source']),
      rejectedReason: _readNullableString(json['rejected_reason']),
      manualConfirmRequired: _readNullableBool(json['manual_confirm_required']),
      autoSellEnabled: _readNullableBool(json['auto_sell_enabled']),
      schedulerRealOrderEnabled:
          _readNullableBool(json['scheduler_real_order_enabled']),
      realOrderSubmitAllowed:
          _readNullableBool(json['real_order_submit_allowed']),
    );
  }
}

class KisOrderSummary {
  const KisOrderSummary({
    required this.openOrders,
    required this.filledToday,
    required this.canceledToday,
    required this.rejectedToday,
    required this.lastOrderAt,
  });

  final int openOrders;
  final int filledToday;
  final int canceledToday;
  final int rejectedToday;
  final String? lastOrderAt;

  static const empty = KisOrderSummary(
    openOrders: 0,
    filledToday: 0,
    canceledToday: 0,
    rejectedToday: 0,
    lastOrderAt: null,
  );

  factory KisOrderSummary.fromJson(Map<String, dynamic> json) {
    return KisOrderSummary(
      openOrders: _readInt(json['open_orders'], 0),
      filledToday: _readInt(json['filled_today'], 0),
      canceledToday: _readInt(json['canceled_today'], 0),
      rejectedToday: _readInt(json['rejected_today'], 0),
      lastOrderAt: _readNullableString(json['last_order_at']),
    );
  }
}

class KisOpenOrderSyncResult {
  const KisOpenOrderSyncResult({required this.count, required this.orders});

  final int? count;
  final List<KisManualOrderResult> orders;

  factory KisOpenOrderSyncResult.fromJson(Map<String, dynamic> json) {
    final rawOrders = json['orders'] as List<dynamic>? ?? const [];
    return KisOpenOrderSyncResult(
      count: json.containsKey('count') ? _readInt(json['count'], 0) : null,
      orders: rawOrders
          .whereType<Map>()
          .map((item) =>
              KisManualOrderResult.fromJson(Map<String, dynamic>.from(item)))
          .toList(),
    );
  }
}

bool isTerminalKisStatus(String status) {
  switch (status.trim().toUpperCase()) {
    case 'FILLED':
    case 'REJECTED':
    case 'REJECTED_BY_SAFETY_GATE':
    case 'CANCELED':
    case 'CANCELLED':
    case 'FAILED':
      return true;
  }
  return false;
}

bool isSyncableKisStatus(String status) {
  switch (status.trim().toUpperCase()) {
    case 'SUBMITTED':
    case 'ACCEPTED':
    case 'PARTIALLY_FILLED':
    case 'UNKNOWN_STALE':
    case 'SYNC_FAILED':
      return true;
  }
  return false;
}

String clearKisStatusLabel(String status) {
  final normalized = status.trim().toUpperCase();
  if (normalized == 'FILLED') return 'FILLED';
  if (normalized == 'CANCELED' || normalized == 'CANCELLED') return 'CANCELED';
  if (normalized == 'FAILED' ||
      normalized == 'REJECTED' ||
      normalized == 'REJECTED_BY_SAFETY_GATE') {
    return 'REJECTED';
  }
  if (isSyncableKisStatus(normalized) ||
      normalized == 'REQUESTED' ||
      normalized == 'PENDING' ||
      normalized == 'PENDING_SUBMIT') {
    return 'SUBMITTED';
  }
  return 'UNKNOWN';
}

int _readInt(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty) return null;
  return double.tryParse(text);
}

String _readString(Object? value, String fallback) {
  final text = value?.toString();
  if (text == null || text.isEmpty) return fallback;
  return text;
}

String? _readNullableString(Object? value) {
  final raw = value?.toString();
  if (raw == null) return null;
  final text = raw.trim();
  if (text.isEmpty || text == 'null') return null;
  return text;
}

bool? _readNullableBool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}
