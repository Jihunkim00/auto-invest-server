class AgentChatLiveOrderAction {
  const AgentChatLiveOrderAction({
    required this.actionId,
    required this.status,
    required this.symbol,
    required this.side,
    required this.orderType,
    required this.provider,
    required this.market,
    required this.currency,
    this.actionType = 'chat_confirmed_live_order',
    this.symbolName,
    this.quantity,
    this.notionalAmount,
    this.estimatedPrice,
    this.estimatedNotional,
    this.expiresAt,
    this.confirmationPhrase,
    this.confirmationToken,
    this.relatedOrderId,
    this.brokerOrderId,
    this.safety = const {},
    this.raw = const {},
  });

  final int actionId;
  final String status;
  final String actionType;
  final String provider;
  final String market;
  final String symbol;
  final String? symbolName;
  final String side;
  final String orderType;
  final double? quantity;
  final double? notionalAmount;
  final String currency;
  final double? estimatedPrice;
  final double? estimatedNotional;
  final String? expiresAt;
  final String? confirmationPhrase;
  final String? confirmationToken;
  final int? relatedOrderId;
  final String? brokerOrderId;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> raw;

  bool get isPending => status == 'pending_confirmation';
  bool get isTerminal =>
      status == 'submitted' ||
      status == 'blocked' ||
      status == 'expired' ||
      status == 'cancelled' ||
      status == 'failed';

  String get displayName {
    final name = symbolName?.trim();
    if (name != null && name.isNotEmpty && name != symbol) {
      return '$name($symbol)';
    }
    return symbol;
  }

  factory AgentChatLiveOrderAction.fromJson(Map<String, dynamic> json) {
    return AgentChatLiveOrderAction(
      actionId: _readInt(json['action_id'], 0),
      status: _readString(json['status'], 'unknown'),
      actionType: _readString(
        json['action_type'],
        'chat_confirmed_live_order',
      ),
      provider: _readString(json['provider'], 'kis'),
      market: _readString(json['market'], 'KR'),
      symbol: _readString(json['symbol'], ''),
      symbolName: _readNullableString(json['symbol_name']),
      side: _readString(json['side'], 'buy'),
      orderType: _readString(json['order_type'], 'market'),
      quantity: _readNullableDouble(json['quantity']),
      notionalAmount: _readNullableDouble(json['notional_amount']),
      currency: _readString(json['currency'], 'KRW'),
      estimatedPrice: _readNullableDouble(json['estimated_price']),
      estimatedNotional: _readNullableDouble(json['estimated_notional']),
      expiresAt: _readNullableString(json['expires_at']),
      confirmationPhrase: _readNullableString(json['confirmation_phrase']),
      confirmationToken: _readNullableString(json['confirmation_token']),
      relatedOrderId: _readNullableInt(json['related_order_id']),
      brokerOrderId: _readNullableString(json['broker_order_id']),
      safety: _readMap(json['safety']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class AgentChatLiveOrderResponse {
  const AgentChatLiveOrderResponse({
    required this.status,
    required this.answer,
    required this.safety,
    required this.diagnostics,
    this.liveOrderAction,
    this.order,
    this.assistantMessageId,
  });

  final String status;
  final AgentChatLiveOrderAnswer answer;
  final AgentChatLiveOrderAction? liveOrderAction;
  final Map<String, dynamic>? order;
  final Map<String, dynamic> safety;
  final int? assistantMessageId;
  final Map<String, dynamic> diagnostics;

  factory AgentChatLiveOrderResponse.fromJson(Map<String, dynamic> json) {
    final actionJson = json['live_order_action'];
    final orderJson = json['order'];
    return AgentChatLiveOrderResponse(
      status: _readString(json['status'], 'unknown'),
      answer: AgentChatLiveOrderAnswer.fromJson(_readMap(json['answer'])),
      liveOrderAction: actionJson is Map
          ? AgentChatLiveOrderAction.fromJson(
              Map<String, dynamic>.from(actionJson),
            )
          : null,
      order: orderJson is Map ? Map<String, dynamic>.from(orderJson) : null,
      safety: _readMap(json['safety']),
      assistantMessageId: _readNullableInt(json['assistant_message_id']),
      diagnostics: _readMap(json['diagnostics']),
    );
  }
}

class AgentChatLiveOrderAnswer {
  const AgentChatLiveOrderAnswer({
    required this.role,
    required this.text,
    required this.answerType,
  });

  final String role;
  final String text;
  final String answerType;

  factory AgentChatLiveOrderAnswer.fromJson(Map<String, dynamic> json) {
    return AgentChatLiveOrderAnswer(
      role: _readString(json['role'], 'assistant'),
      text: _readString(json['text'], ''),
      answerType: _readString(json['answer_type'], 'live_order_blocked'),
    );
  }
}

Map<String, dynamic> _readMap(Object? value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

String _readString(Object? value, String fallback) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return fallback;
  return text;
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

int _readInt(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString());
}
