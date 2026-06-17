class AgentLivePrefill {
  const AgentLivePrefill({
    required this.status,
    required this.planId,
    required this.planRunId,
    required this.commandType,
    required this.result,
    required this.auth,
    required this.safety,
    this.prefill,
  });

  final String status;
  final int planId;
  final int planRunId;
  final String commandType;
  final Map<String, dynamic> result;
  final AgentManualTicketPrefill? prefill;
  final Map<String, dynamic> auth;
  final Map<String, dynamic> safety;

  bool get isReady => status == 'manual_ticket_prefill_ready';
  bool get requiresAuth => status == 'auth_required';
  bool get isBlocked => status == 'blocked';

  factory AgentLivePrefill.fromJson(Map<String, dynamic> json) {
    final prefillJson = json['prefill'];
    return AgentLivePrefill(
      status: _readString(json['status'], 'blocked'),
      planId: _readInt(json['plan_id'], 0),
      planRunId: _readInt(json['plan_run_id'], 0),
      commandType: _readString(json['command_type'], ''),
      result: _readMap(json['result']),
      prefill: prefillJson is Map
          ? AgentManualTicketPrefill.fromJson(
              Map<String, dynamic>.from(prefillJson),
            )
          : null,
      auth: _readMap(json['auth']),
      safety: _readMap(json['safety']),
    );
  }
}

class AgentManualTicketPrefill {
  const AgentManualTicketPrefill({
    required this.provider,
    required this.market,
    required this.symbol,
    required this.side,
    required this.orderType,
    required this.dryRun,
    required this.confirmLive,
    required this.sourceContext,
    required this.sourceMetadata,
    this.quantity,
    this.qty,
    this.notional,
    this.currency,
  });

  final String provider;
  final String market;
  final String symbol;
  final String side;
  final String orderType;
  final bool dryRun;
  final bool confirmLive;
  final String sourceContext;
  final Map<String, dynamic> sourceMetadata;
  final double? quantity;
  final int? qty;
  final double? notional;
  final String? currency;

  factory AgentManualTicketPrefill.fromJson(Map<String, dynamic> json) {
    return AgentManualTicketPrefill(
      provider: _readString(json['provider'], ''),
      market: _readString(json['market'], ''),
      symbol: _readString(json['symbol'], ''),
      side: _readString(json['side'], ''),
      quantity: _readNullableDouble(json['quantity']),
      qty: _readNullableInt(json['qty']),
      notional: _readNullableDouble(json['notional']),
      currency: _readNullableString(json['currency']),
      orderType: _readString(json['order_type'], 'market'),
      dryRun: json['dry_run'] != false,
      confirmLive: json['confirm_live'] == true,
      sourceContext:
          _readString(json['source_context'], 'agent_manual_prefill'),
      sourceMetadata: _readMap(json['source_metadata']),
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
  if (text == null || text.isEmpty) return null;
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
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty) return null;
  return double.tryParse(text);
}
