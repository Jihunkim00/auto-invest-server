class PortfolioSummary {
  const PortfolioSummary({
    required this.currency,
    required this.positionsCount,
    required this.pendingOrdersCount,
    required this.totalCostBasis,
    required this.totalMarketValue,
    required this.totalUnrealizedPl,
    required this.totalUnrealizedPlpc,
    required this.cash,
    required this.positions,
    required this.pendingOrders,
  });

  factory PortfolioSummary.empty({String currency = 'USD'}) => PortfolioSummary(
        currency: currency,
        positionsCount: 0,
        pendingOrdersCount: 0,
        totalCostBasis: 0,
        totalMarketValue: 0,
        totalUnrealizedPl: 0,
        totalUnrealizedPlpc: 0,
        cash: 0,
        positions: [],
        pendingOrders: [],
      );

  factory PortfolioSummary.fromJson(Map<String, dynamic> json) {
    final rawPositions = json['positions'] as List<dynamic>? ?? const [];
    final rawOrders = json['pending_orders'] as List<dynamic>? ?? const [];

    return PortfolioSummary(
      currency: _readString(json['currency'], 'USD'),
      positionsCount: _readInt(json['positions_count'], rawPositions.length),
      pendingOrdersCount:
          _readInt(json['pending_orders_count'], rawOrders.length),
      totalCostBasis: _readDouble(json['total_cost_basis']),
      totalMarketValue: _readDouble(json['total_market_value']),
      totalUnrealizedPl: _readDouble(json['total_unrealized_pl']),
      totalUnrealizedPlpc: _readDouble(json['total_unrealized_plpc']),
      cash: _readDouble(json['cash']),
      positions: rawPositions
          .whereType<Map>()
          .map((item) => PositionSummary.fromJson(
              Map<String, dynamic>.from(item.cast<String, dynamic>())))
          .toList(),
      pendingOrders: rawOrders
          .whereType<Map>()
          .map((item) => PendingOrderSummary.fromJson(
              Map<String, dynamic>.from(item.cast<String, dynamic>())))
          .toList(),
    );
  }

  final String currency;
  final int positionsCount;
  final int pendingOrdersCount;
  final double totalCostBasis;
  final double totalMarketValue;
  final double totalUnrealizedPl;
  final double totalUnrealizedPlpc;
  final double cash;
  final List<PositionSummary> positions;
  final List<PendingOrderSummary> pendingOrders;
}

class PositionSummary {
  const PositionSummary({
    required this.symbol,
    this.name = '',
    required this.side,
    required this.qty,
    required this.avgEntryPrice,
    required this.costBasis,
    required this.currentPrice,
    required this.marketValue,
    required this.unrealizedPl,
    required this.unrealizedPlpc,
  });

  factory PositionSummary.fromJson(Map<String, dynamic> json) {
    return PositionSummary(
      symbol: _readString(json['symbol'], ''),
      name: _readString(json['name'], ''),
      side: _readString(json['side'], 'long'),
      qty: _readDouble(json['qty']),
      avgEntryPrice: _readDouble(json['avg_entry_price']),
      costBasis: _readDouble(json['cost_basis']),
      currentPrice: _readNullableDouble(json['current_price']),
      marketValue: _readDouble(json['market_value']),
      unrealizedPl: _readDouble(json['unrealized_pl']),
      unrealizedPlpc: _readDouble(json['unrealized_plpc']),
    );
  }

  final String symbol;
  final String name;
  final String side;
  final double qty;
  final double avgEntryPrice;
  final double costBasis;
  final double? currentPrice;
  final double marketValue;
  final double unrealizedPl;
  final double unrealizedPlpc;
}

class PendingOrderSummary {
  const PendingOrderSummary({
    required this.id,
    required this.symbol,
    this.name = '',
    required this.side,
    required this.type,
    required this.status,
    required this.qty,
    this.unfilledQty,
    required this.notional,
    required this.limitPrice,
    this.price,
    required this.estimatedAmount,
    required this.submittedAt,
  });

  factory PendingOrderSummary.fromJson(Map<String, dynamic> json) {
    return PendingOrderSummary(
      id: _readString(json['id'] ?? json['order_id'], ''),
      symbol: _readString(json['symbol'], ''),
      name: _readString(json['name'], ''),
      side: _readString(json['side'], ''),
      type: _readString(json['type'] ?? json['order_type'], ''),
      status: _readString(json['status'], ''),
      qty: _readNullableDouble(json['qty']),
      unfilledQty: _readNullableDouble(json['unfilled_qty']),
      notional: _readNullableDouble(json['notional']),
      limitPrice: _readNullableDouble(json['limit_price']),
      price: _readNullableDouble(json['price']),
      estimatedAmount: _readNullableDouble(json['estimated_amount']),
      submittedAt: _readNullableString(json['submitted_at']),
    );
  }

  final String id;
  final String symbol;
  final String name;
  final String side;
  final String type;
  final String status;
  final double? qty;
  final double? unfilledQty;
  final double? notional;
  final double? limitPrice;
  final double? price;
  final double? estimatedAmount;
  final String? submittedAt;
}

int _readInt(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

double _readDouble(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? 0;
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString();
  if (text.isEmpty) return null;
  return double.tryParse(text);
}

String _readString(Object? value, String fallback) {
  final text = value?.toString();
  if (text == null || text.isEmpty) return fallback;
  return text;
}

String? _readNullableString(Object? value) {
  final text = value?.toString();
  if (text == null || text.isEmpty) return null;
  return text;
}
