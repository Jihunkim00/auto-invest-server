import 'user_broker_account_snapshot.dart';

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
    this.totalAssetValue,
    this.stockEvaluationAmount,
    this.cashBalance,
    this.withdrawableCash,
    this.orderableCash,
    this.orderableCashStatus,
    this.orderableCashSource,
    this.d1Cash,
    this.d2Cash,
    this.cashKnown = true,
    this.balanceUnavailable = false,
    this.positionsUnavailable = false,
    this.openOrdersUnavailable = false,
    this.kisAuthErrorMessage,
    this.nextRefreshAllowedAt,
    this.tokenExpired = false,
  });

  factory PortfolioSummary.empty({
    String currency = 'USD',
    bool cashKnown = true,
    bool balanceUnavailable = false,
    bool positionsUnavailable = false,
    bool openOrdersUnavailable = false,
    String? kisAuthErrorMessage,
    String? nextRefreshAllowedAt,
    bool tokenExpired = false,
  }) =>
      PortfolioSummary(
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
        cashKnown: cashKnown,
        balanceUnavailable: balanceUnavailable,
        positionsUnavailable: positionsUnavailable,
        openOrdersUnavailable: openOrdersUnavailable,
        kisAuthErrorMessage: kisAuthErrorMessage,
        nextRefreshAllowedAt: nextRefreshAllowedAt,
        tokenExpired: tokenExpired,
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
      totalAssetValue: _readNullableDouble(json['total_asset_value']),
      stockEvaluationAmount:
          _readNullableDouble(json['stock_evaluation_amount']),
      cashBalance: _readNullableDouble(json['cash_balance']) ??
          _readNullableDouble(json['cash']),
      withdrawableCash: _readNullableDouble(json['withdrawable_cash']),
      orderableCash: _readNullableDouble(json['orderable_cash']),
      orderableCashStatus: _readNullableString(json['orderable_cash_status']),
      orderableCashSource: _readNullableString(json['orderable_cash_source']),
      d1Cash: _readNullableDouble(json['d1_cash']),
      d2Cash: _readNullableDouble(json['d2_cash']),
      cashKnown: _readBool(json['cash_known'], true),
      balanceUnavailable: _readBool(json['balance_unavailable'], false),
      positionsUnavailable: _readBool(json['positions_unavailable'], false),
      openOrdersUnavailable: _readBool(json['open_orders_unavailable'], false),
      kisAuthErrorMessage: _readNullableString(json['kis_auth_error_message']),
      nextRefreshAllowedAt:
          _readNullableString(json['next_refresh_allowed_at']),
      tokenExpired: _readBool(json['token_expired'], false),
    );
  }

  factory PortfolioSummary.fromUserBrokerAccount(
    UserBrokerAccountSnapshot snapshot,
  ) {
    final account = snapshot.account;
    final positions = snapshot.positions
        .map(
          (position) => PositionSummary(
            symbol: position.symbol,
            name: position.name ?? '',
            broker: snapshot.provider,
            market:
                snapshot.provider.trim().toLowerCase() == 'kis' ? 'KR' : 'US',
            side: 'long',
            qty: position.quantity ?? 0,
            avgEntryPrice: position.avgPrice ?? 0,
            costBasis: position.costBasis ?? 0,
            currentPrice: position.currentPrice,
            marketValue: position.marketValue ?? 0,
            unrealizedPl: position.unrealizedPl ?? 0,
            unrealizedPlpc: position.unrealizedPlPct ?? 0,
          ),
        )
        .toList();
    final pendingOrders = snapshot.openOrders
        .map(
          (order) => PendingOrderSummary(
            id: order.brokerOrderId,
            symbol: order.symbol,
            name: order.name ?? '',
            side: order.side,
            type: order.orderType ?? '',
            status: order.status,
            qty: order.quantity,
            unfilledQty: order.remainingQuantity,
            notional: order.orderPrice == null || order.quantity == null
                ? null
                : order.orderPrice! * order.quantity!,
            limitPrice: order.orderPrice,
            price: order.orderPrice,
            estimatedAmount: order.orderPrice == null || order.quantity == null
                ? null
                : order.orderPrice! * order.quantity!,
            submittedAt: order.submittedAt,
          ),
        )
        .toList();
    final totalCostBasis = positions.fold<double>(
      0,
      (total, position) => total + position.costBasis,
    );
    final totalMarketValue = positions.fold<double>(
      0,
      (total, position) => total + position.marketValue,
    );
    final totalUnrealizedPl = account.unrealizedPl ??
        positions.fold<double>(
          0,
          (total, position) => total + position.unrealizedPl,
        );
    final totalUnrealizedPlpc = account.unrealizedPlPct ??
        (totalCostBasis == 0 ? 0 : totalUnrealizedPl / totalCostBasis * 100);
    final isKis = snapshot.provider.trim().toLowerCase() == 'kis';

    return PortfolioSummary(
      currency: account.currency,
      positionsCount: positions.length,
      pendingOrdersCount: pendingOrders.length,
      totalCostBasis: totalCostBasis,
      totalMarketValue: totalMarketValue,
      totalUnrealizedPl: totalUnrealizedPl,
      totalUnrealizedPlpc: totalUnrealizedPlpc,
      cash: account.cash ?? 0,
      positions: positions,
      pendingOrders: pendingOrders,
      totalAssetValue: account.portfolioValue ?? account.equity,
      stockEvaluationAmount:
          account.stockEvaluationAmount ?? (isKis ? totalMarketValue : null),
      cashBalance: account.cash,
      withdrawableCash: account.withdrawableCash,
      orderableCash: account.buyingPower,
      d1Cash: account.d1Cash,
      d2Cash: account.d2Cash,
      cashKnown: account.cash != null,
      balanceUnavailable: !snapshot.connected,
      positionsUnavailable: !snapshot.connected,
      openOrdersUnavailable: !snapshot.connected,
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
  final double? totalAssetValue;
  final double? stockEvaluationAmount;
  final double? cashBalance;
  final double? withdrawableCash;
  final double? orderableCash;
  final String? orderableCashStatus;
  final String? orderableCashSource;
  final double? d1Cash;
  final double? d2Cash;
  final bool cashKnown;
  final bool balanceUnavailable;
  final bool positionsUnavailable;
  final bool openOrdersUnavailable;
  final String? kisAuthErrorMessage;
  final String? nextRefreshAllowedAt;
  final bool tokenExpired;

  bool get hasUnavailableKisData =>
      balanceUnavailable || positionsUnavailable || openOrdersUnavailable;
}

class PositionSummary {
  const PositionSummary({
    required this.symbol,
    this.name = '',
    this.broker = '',
    this.market = '',
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
    final symbol = _readString(json['symbol'], '');
    return PositionSummary(
      symbol: symbol,
      name: _companyName(json, symbol),
      broker: _readString(json['broker'] ?? json['provider'], ''),
      market: _readString(json['market'], ''),
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
  final String broker;
  final String market;
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
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return fallback;
  return text;
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

bool _readBool(Object? value, bool fallback) {
  if (value is bool) return value;
  final text = value?.toString().trim().toLowerCase();
  if (text == 'true') return true;
  if (text == 'false') return false;
  return fallback;
}

String _companyName(Map<String, dynamic> json, String symbol) {
  final value = _firstDistinctString([
    json['company_name'],
    json['companyName'],
    json['name'],
    json['company'],
    json['asset_name'],
  ], symbol);
  return value ?? (symbol.isNotEmpty ? symbol : 'Unknown Company');
}

String? _firstDistinctString(List<Object?> values, String symbol) {
  for (final value in values) {
    final text = _readNullableString(value);
    if (text == null) continue;
    if (symbol.isNotEmpty && text.toUpperCase() == symbol.toUpperCase()) {
      continue;
    }
    final lower = text.toLowerCase();
    if (lower == 'unknown company' || lower == 'unknown') continue;
    return text;
  }
  return null;
}
