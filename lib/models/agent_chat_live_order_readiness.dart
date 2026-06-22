class AgentChatLiveOrderReadiness {
  const AgentChatLiveOrderReadiness({
    required this.status,
    required this.ready,
    required this.readyForChatConfirmedLiveOrder,
    required this.provider,
    required this.market,
    required this.summary,
    required this.checks,
    required this.limits,
    required this.capabilities,
    required this.safety,
    this.blockingReasons = const [],
    this.runtime = const {},
    this.marketSession = const {},
    this.raw = const {},
  });

  final String status;
  final bool ready;
  final bool readyForChatConfirmedLiveOrder;
  final String provider;
  final String market;
  final String summary;
  final List<AgentChatLiveOrderReadinessCheck> checks;
  final List<Map<String, dynamic>> blockingReasons;
  final AgentChatLiveOrderLimits limits;
  final AgentChatLiveOrderCapabilities capabilities;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> runtime;
  final Map<String, dynamic> marketSession;
  final Map<String, dynamic> raw;

  bool get isBlocked => !ready;

  List<AgentChatLiveOrderReadinessCheck> get blockingChecks => checks
      .where((check) => check.severity == 'blocking' && !check.ok)
      .toList(growable: false);

  factory AgentChatLiveOrderReadiness.fromJson(Map<String, dynamic> json) {
    final checks = json['checks'] as List<dynamic>? ?? const [];
    final blockingReasons =
        json['blocking_reasons'] as List<dynamic>? ?? const [];
    return AgentChatLiveOrderReadiness(
      status: _readString(json['status'], 'blocked'),
      ready: _readBool(json['ready']),
      readyForChatConfirmedLiveOrder:
          _readBool(json['ready_for_chat_confirmed_live_order']),
      provider: _readString(json['provider'], 'kis'),
      market: _readString(json['market'], 'KR'),
      summary: _readString(json['summary'], ''),
      checks: [
        for (final item in checks)
          if (item is Map)
            AgentChatLiveOrderReadinessCheck.fromJson(
              Map<String, dynamic>.from(item),
            ),
      ],
      blockingReasons: [
        for (final item in blockingReasons)
          if (item is Map) Map<String, dynamic>.from(item),
      ],
      limits: AgentChatLiveOrderLimits.fromJson(_readMap(json['limits'])),
      capabilities:
          AgentChatLiveOrderCapabilities.fromJson(_readMap(json['capabilities'])),
      safety: _readMap(json['safety']),
      runtime: _readMap(json['runtime']),
      marketSession: _readMap(json['market_session']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class AgentChatLiveOrderReadinessCheck {
  const AgentChatLiveOrderReadinessCheck({
    required this.key,
    required this.label,
    required this.ok,
    required this.value,
    required this.severity,
    required this.message,
  });

  final String key;
  final String label;
  final bool ok;
  final Object? value;
  final String severity;
  final String message;

  factory AgentChatLiveOrderReadinessCheck.fromJson(
    Map<String, dynamic> json,
  ) {
    return AgentChatLiveOrderReadinessCheck(
      key: _readString(json['key'], ''),
      label: _readString(json['label'], ''),
      ok: _readBool(json['ok']),
      value: json['value'],
      severity: _readString(json['severity'], 'ok'),
      message: _readString(json['message'], ''),
    );
  }
}

class AgentChatLiveOrderLimits {
  const AgentChatLiveOrderLimits({
    required this.maxOrdersPerDay,
    required this.ordersUsedToday,
    required this.ordersRemainingToday,
    this.maxNotionalKrw,
    this.maxNotionalPct,
  });

  final int maxOrdersPerDay;
  final int ordersUsedToday;
  final int ordersRemainingToday;
  final double? maxNotionalKrw;
  final double? maxNotionalPct;

  factory AgentChatLiveOrderLimits.fromJson(Map<String, dynamic> json) {
    return AgentChatLiveOrderLimits(
      maxOrdersPerDay: _readInt(json['max_orders_per_day'], 0),
      ordersUsedToday: _readInt(json['orders_used_today'], 0),
      ordersRemainingToday: _readInt(json['orders_remaining_today'], 0),
      maxNotionalKrw: _readNullableDouble(json['max_notional_krw']),
      maxNotionalPct: _readNullableDouble(json['max_notional_pct']),
    );
  }
}

class AgentChatLiveOrderCapabilities {
  const AgentChatLiveOrderCapabilities({
    required this.buyEnabled,
    required this.sellEnabled,
    required this.marketOrderEnabled,
    required this.limitOrderEnabled,
  });

  final bool buyEnabled;
  final bool sellEnabled;
  final bool marketOrderEnabled;
  final bool limitOrderEnabled;

  factory AgentChatLiveOrderCapabilities.fromJson(Map<String, dynamic> json) {
    return AgentChatLiveOrderCapabilities(
      buyEnabled: _readBool(json['buy_enabled']),
      sellEnabled: _readBool(json['sell_enabled']),
      marketOrderEnabled: _readBool(json['market_order_enabled']),
      limitOrderEnabled: _readBool(json['limit_order_enabled']),
    );
  }
}

class AgentChatLiveOrderSettingsApplyResult {
  const AgentChatLiveOrderSettingsApplyResult({
    required this.status,
    required this.applied,
    required this.changedKeys,
    required this.unchangedKeys,
    required this.safety,
    required this.settings,
    this.preset,
    this.auditId,
    this.readiness,
    this.warningMessage,
    this.raw = const {},
  });

  final String status;
  final bool applied;
  final String? preset;
  final List<String> changedKeys;
  final List<String> unchangedKeys;
  final int? auditId;
  final AgentChatLiveOrderReadiness? readiness;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> settings;
  final String? warningMessage;
  final Map<String, dynamic> raw;

  factory AgentChatLiveOrderSettingsApplyResult.fromJson(
    Map<String, dynamic> json,
  ) {
    final readinessJson = json['readiness'];
    return AgentChatLiveOrderSettingsApplyResult(
      status: _readString(json['status'], 'updated'),
      applied: _readBool(json['applied']),
      preset: _readNullableString(json['preset']),
      changedKeys: _readStringList(json['changed_keys']),
      unchangedKeys: _readStringList(json['unchanged_keys']),
      auditId: _readNullableInt(json['audit_id']),
      readiness: readinessJson is Map
          ? AgentChatLiveOrderReadiness.fromJson(
              Map<String, dynamic>.from(readinessJson),
            )
          : null,
      safety: _readMap(json['safety']),
      settings: _readMap(json['settings']),
      warningMessage: _readNullableString(json['warning_message']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

Map<String, dynamic> _readMap(Object? value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
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

bool _readBool(Object? value) {
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value?.toString().trim().toLowerCase();
  return text == 'true' || text == '1' || text == 'yes';
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
  return double.tryParse(value.toString().replaceAll(',', ''));
}

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (_readNullableString(item) != null) _readNullableString(item)!,
  ];
}
