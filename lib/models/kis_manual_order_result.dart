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
    required this.submittedAt,
    required this.lastSyncedAt,
    required this.syncError,
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
  final String? submittedAt;
  final String? lastSyncedAt;
  final String? syncError;

  bool get hasSyncError => syncError != null && syncError!.isNotEmpty;
  bool get isFilled => internalStatus.toUpperCase() == 'FILLED';
  bool get isPartial => internalStatus.toUpperCase() == 'PARTIALLY_FILLED';
  bool get isAccepted => internalStatus.toUpperCase() == 'ACCEPTED';
  bool get isUnknownStale => internalStatus.toUpperCase() == 'UNKNOWN_STALE';

  factory KisManualOrderResult.fromJson(Map<String, dynamic> json) {
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
      internalStatus: _readString(json['internal_status'], 'UNKNOWN'),
      brokerOrderStatus: _readNullableString(
          json['broker_order_status'] ?? json['broker_status']),
      submittedAt: _readNullableString(json['submitted_at']),
      lastSyncedAt: _readNullableString(json['last_synced_at']),
      syncError: _readNullableString(json['sync_error']),
    );
  }
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
