class UserBrokerAccountSnapshot {
  const UserBrokerAccountSnapshot({
    required this.provider,
    required this.environment,
    required this.connected,
    required this.connectionStatus,
    required this.account,
    required this.positions,
    required this.openOrders,
    this.fetchedAt,
  });

  final String provider;
  final String environment;
  final bool connected;
  final String connectionStatus;
  final DateTime? fetchedAt;
  final UserBrokerAccountSummary account;
  final List<UserBrokerPosition> positions;
  final List<UserBrokerOpenOrder> openOrders;

  factory UserBrokerAccountSnapshot.fromJson(Map<String, dynamic> json) {
    final rawAccount = json['account'];
    final rawPositions = json['positions'];
    final rawOrders = json['open_orders'];
    return UserBrokerAccountSnapshot(
      provider: _readString(json['provider']) ?? '',
      environment: _readString(json['environment']) ?? '',
      connected: json['connected'] == true,
      connectionStatus: _readString(json['connection_status']) ?? 'unknown',
      fetchedAt: _readDateTime(json['fetched_at']),
      account: UserBrokerAccountSummary.fromJson(
        rawAccount is Map ? Map<String, dynamic>.from(rawAccount) : const {},
      ),
      positions: rawPositions is List
          ? rawPositions
              .whereType<Map>()
              .map((item) => UserBrokerPosition.fromJson(
                    Map<String, dynamic>.from(item),
                  ))
              .toList()
          : const [],
      openOrders: rawOrders is List
          ? rawOrders
              .whereType<Map>()
              .map((item) => UserBrokerOpenOrder.fromJson(
                    Map<String, dynamic>.from(item),
                  ))
              .toList()
          : const [],
    );
  }
}

class UserBrokerAccountSummary {
  const UserBrokerAccountSummary({
    this.currency = 'USD',
    this.cash,
    this.buyingPower,
    this.equity,
    this.portfolioValue,
    this.stockEvaluationAmount,
    this.withdrawableCash,
    this.d1Cash,
    this.d2Cash,
    this.unrealizedPl,
    this.unrealizedPlPct,
  });

  final String currency;
  final double? cash;
  final double? buyingPower;
  final double? equity;
  final double? portfolioValue;
  final double? stockEvaluationAmount;
  final double? withdrawableCash;
  final double? d1Cash;
  final double? d2Cash;
  final double? unrealizedPl;
  final double? unrealizedPlPct;

  factory UserBrokerAccountSummary.fromJson(Map<String, dynamic> json) {
    return UserBrokerAccountSummary(
      currency: _readString(json['currency']) ?? 'USD',
      cash: _readDouble(json['cash']),
      buyingPower: _readDouble(json['buying_power']),
      equity: _readDouble(json['equity']),
      portfolioValue: _readDouble(json['portfolio_value']),
      stockEvaluationAmount: _readDouble(json['stock_evaluation_amount']),
      withdrawableCash: _readDouble(json['withdrawable_cash']),
      d1Cash: _readDouble(json['d1_cash']),
      d2Cash: _readDouble(json['d2_cash']),
      unrealizedPl: _readDouble(json['unrealized_pl']),
      unrealizedPlPct: _readDouble(json['unrealized_pl_pct']),
    );
  }
}

class UserBrokerPosition {
  const UserBrokerPosition({
    required this.symbol,
    this.name,
    this.quantity,
    this.availableQuantity,
    this.avgPrice,
    this.currentPrice,
    this.marketValue,
    this.costBasis,
    this.unrealizedPl,
    this.unrealizedPlPct,
  });

  final String symbol;
  final String? name;
  final double? quantity;
  final double? availableQuantity;
  final double? avgPrice;
  final double? currentPrice;
  final double? marketValue;
  final double? costBasis;
  final double? unrealizedPl;
  final double? unrealizedPlPct;

  factory UserBrokerPosition.fromJson(Map<String, dynamic> json) {
    return UserBrokerPosition(
      symbol: _readString(json['symbol']) ?? '',
      name: _readString(json['name']),
      quantity: _readDouble(json['quantity']),
      availableQuantity: _readDouble(json['available_quantity']),
      avgPrice: _readDouble(json['avg_price']),
      currentPrice: _readDouble(json['current_price']),
      marketValue: _readDouble(json['market_value']),
      costBasis: _readDouble(json['cost_basis']),
      unrealizedPl: _readDouble(json['unrealized_pl']),
      unrealizedPlPct: _readDouble(json['unrealized_pl_pct']),
    );
  }
}

class UserBrokerOpenOrder {
  const UserBrokerOpenOrder({
    required this.brokerOrderId,
    required this.symbol,
    this.name,
    this.side = 'unknown',
    this.quantity,
    this.filledQuantity,
    this.remainingQuantity,
    this.orderPrice,
    this.orderType,
    this.status = '',
    this.submittedAt,
  });

  final String brokerOrderId;
  final String symbol;
  final String? name;
  final String side;
  final double? quantity;
  final double? filledQuantity;
  final double? remainingQuantity;
  final double? orderPrice;
  final String? orderType;
  final String status;
  final String? submittedAt;

  factory UserBrokerOpenOrder.fromJson(Map<String, dynamic> json) {
    return UserBrokerOpenOrder(
      brokerOrderId: _readString(json['broker_order_id']) ?? '',
      symbol: _readString(json['symbol']) ?? '',
      name: _readString(json['name']),
      side: _readString(json['side']) ?? 'unknown',
      quantity: _readDouble(json['quantity']),
      filledQuantity: _readDouble(json['filled_quantity']),
      remainingQuantity: _readDouble(json['remaining_quantity']),
      orderPrice: _readDouble(json['order_price']),
      orderType: _readString(json['order_type']),
      status: _readString(json['status']) ?? '',
      submittedAt: _readString(json['submitted_at']),
    );
  }
}

String? _readString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty || text == 'null' ? null : text;
}

double? _readDouble(Object? value) {
  if (value is num) return value.toDouble();
  final text = value?.toString().trim().replaceAll(',', '');
  if (text == null || text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}

DateTime? _readDateTime(Object? value) {
  final text = _readString(value);
  return text == null ? null : DateTime.tryParse(text);
}
