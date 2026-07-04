class PositionLifecycle {
  const PositionLifecycle({
    required this.provider,
    required this.market,
    this.generatedAt,
    required this.items,
    required this.totals,
    required this.safety,
    required this.auditFlags,
  });

  factory PositionLifecycle.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    return PositionLifecycle(
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      generatedAt: _nullableDateTime(json['generated_at']),
      items: rawItems is List
          ? [
              for (final item in rawItems)
                if (item is Map)
                  PositionLifecycleItem.fromJson(
                    Map<String, dynamic>.from(item),
                  ),
            ]
          : const [],
      totals: PositionLifecycleTotals.fromJson(_map(json['totals'])),
      safety: _map(json['safety']),
      auditFlags: _strings(json['audit_flags']),
    );
  }

  final String provider;
  final String market;
  final DateTime? generatedAt;
  final List<PositionLifecycleItem> items;
  final PositionLifecycleTotals totals;
  final Map<String, dynamic> safety;
  final List<String> auditFlags;
}

class PositionLifecycleTotals {
  const PositionLifecycleTotals({
    required this.openPositionCount,
    required this.closedLifecycleCount,
    required this.totalCurrentValue,
    required this.totalUnrealizedPl,
    required this.totalRealizedPl,
    this.totalRealizedPlPct,
    required this.incompleteCalculationCount,
  });

  factory PositionLifecycleTotals.fromJson(Map<String, dynamic> json) {
    return PositionLifecycleTotals(
      openPositionCount: _int(json['open_position_count']),
      closedLifecycleCount: _int(json['closed_lifecycle_count']),
      totalCurrentValue: _double(json['total_current_value']),
      totalUnrealizedPl: _double(json['total_unrealized_pl']),
      totalRealizedPl: _double(json['total_realized_pl']),
      totalRealizedPlPct: _nullableDouble(json['total_realized_pl_pct']),
      incompleteCalculationCount: _int(json['incomplete_calculation_count']),
    );
  }

  final int openPositionCount;
  final int closedLifecycleCount;
  final double totalCurrentValue;
  final double totalUnrealizedPl;
  final double totalRealizedPl;
  final double? totalRealizedPlPct;
  final int incompleteCalculationCount;
}

class PositionLifecycleItem {
  const PositionLifecycleItem({
    required this.lifecycleId,
    required this.symbol,
    this.name,
    required this.provider,
    required this.market,
    required this.lifecycleStatus,
    required this.entrySource,
    this.entryOrderId,
    this.entryBrokerOrderId,
    this.entryKisOdno,
    this.entrySubmittedAt,
    this.entryFilledAt,
    this.entryQuantity,
    this.entryAveragePrice,
    this.entryNotional,
    this.relatedPromotionId,
    this.relatedSignalId,
    this.currentQuantity,
    this.currentPrice,
    this.currentValue,
    this.costBasis,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.exitOrderId,
    this.exitBrokerOrderId,
    this.exitKisOdno,
    this.exitSubmittedAt,
    this.exitFilledAt,
    this.exitQuantity,
    this.exitAveragePrice,
    this.exitNotional,
    this.realizedPl,
    this.realizedPlPct,
    this.fees,
    this.holdingPeriodMinutes,
    this.latestStatus,
    this.latestBrokerStatus,
    required this.riskFlags,
    required this.gatingNotes,
    required this.auditFlags,
    required this.nextSafeAction,
    required this.events,
    required this.rawPayload,
  });

  factory PositionLifecycleItem.fromJson(Map<String, dynamic> json) {
    final rawEvents = json['events'];
    return PositionLifecycleItem(
      lifecycleId: _string(json['lifecycle_id'], ''),
      symbol: _string(json['symbol'], ''),
      name: _nullableString(json['name']),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      lifecycleStatus: _string(json['lifecycle_status'], 'unknown'),
      entrySource: _string(json['entry_source'], 'unknown'),
      entryOrderId: _nullableInt(json['entry_order_id']),
      entryBrokerOrderId: _nullableString(json['entry_broker_order_id']),
      entryKisOdno: _nullableString(json['entry_kis_odno']),
      entrySubmittedAt: _nullableDateTime(json['entry_submitted_at']),
      entryFilledAt: _nullableDateTime(json['entry_filled_at']),
      entryQuantity: _nullableDouble(json['entry_quantity']),
      entryAveragePrice: _nullableDouble(json['entry_average_price']),
      entryNotional: _nullableDouble(json['entry_notional']),
      relatedPromotionId: _nullableInt(json['related_promotion_id']),
      relatedSignalId: _nullableInt(json['related_signal_id']),
      currentQuantity: _nullableDouble(json['current_quantity']),
      currentPrice: _nullableDouble(json['current_price']),
      currentValue: _nullableDouble(json['current_value']),
      costBasis: _nullableDouble(json['cost_basis']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      exitOrderId: _nullableInt(json['exit_order_id']),
      exitBrokerOrderId: _nullableString(json['exit_broker_order_id']),
      exitKisOdno: _nullableString(json['exit_kis_odno']),
      exitSubmittedAt: _nullableDateTime(json['exit_submitted_at']),
      exitFilledAt: _nullableDateTime(json['exit_filled_at']),
      exitQuantity: _nullableDouble(json['exit_quantity']),
      exitAveragePrice: _nullableDouble(json['exit_average_price']),
      exitNotional: _nullableDouble(json['exit_notional']),
      realizedPl: _nullableDouble(json['realized_pl']),
      realizedPlPct: _nullableDouble(json['realized_pl_pct']),
      fees: _nullableDouble(json['fees']),
      holdingPeriodMinutes: _nullableInt(json['holding_period_minutes']),
      latestStatus: _nullableString(json['latest_status']),
      latestBrokerStatus: _nullableString(json['latest_broker_status']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      auditFlags: _strings(json['audit_flags']),
      nextSafeAction: _string(json['next_safe_action'], 'review_audit_trail'),
      events: rawEvents is List
          ? [
              for (final event in rawEvents)
                if (event is Map)
                  PositionLifecycleEvent.fromJson(
                    Map<String, dynamic>.from(event),
                  ),
            ]
          : const [],
      rawPayload: Map<String, dynamic>.from(json),
    );
  }

  final String lifecycleId;
  final String symbol;
  final String? name;
  final String provider;
  final String market;
  final String lifecycleStatus;
  final String entrySource;
  final int? entryOrderId;
  final String? entryBrokerOrderId;
  final String? entryKisOdno;
  final DateTime? entrySubmittedAt;
  final DateTime? entryFilledAt;
  final double? entryQuantity;
  final double? entryAveragePrice;
  final double? entryNotional;
  final int? relatedPromotionId;
  final int? relatedSignalId;
  final double? currentQuantity;
  final double? currentPrice;
  final double? currentValue;
  final double? costBasis;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final int? exitOrderId;
  final String? exitBrokerOrderId;
  final String? exitKisOdno;
  final DateTime? exitSubmittedAt;
  final DateTime? exitFilledAt;
  final double? exitQuantity;
  final double? exitAveragePrice;
  final double? exitNotional;
  final double? realizedPl;
  final double? realizedPlPct;
  final double? fees;
  final int? holdingPeriodMinutes;
  final String? latestStatus;
  final String? latestBrokerStatus;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<String> auditFlags;
  final String nextSafeAction;
  final List<PositionLifecycleEvent> events;
  final Map<String, dynamic> rawPayload;

  bool get isOpen => lifecycleStatus == 'open';
  bool get isClosed => lifecycleStatus == 'closed';
  bool get hasIncompleteCalculation =>
      auditFlags.contains('calculation_incomplete');

  String get displayName {
    final text = name?.trim() ?? '';
    return text.isEmpty ? symbol : '$symbol $text';
  }
}

class PositionLifecycleEvent {
  const PositionLifecycleEvent({
    this.timestamp,
    required this.eventType,
    required this.title,
    this.status,
    this.source,
    this.relatedId,
    this.summary,
    required this.safetyFlags,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
  });

  factory PositionLifecycleEvent.fromJson(Map<String, dynamic> json) {
    return PositionLifecycleEvent(
      timestamp: _nullableDateTime(json['timestamp']),
      eventType: _string(json['event_type'], 'unknown'),
      title: _string(json['title'], ''),
      status: _nullableString(json['status']),
      source: _nullableString(json['source']),
      relatedId: _nullableString(json['related_id']),
      summary: _nullableString(json['summary']),
      safetyFlags: _strings(json['safety_flags']),
      realOrderSubmitted: json['real_order_submitted'] == true,
      brokerSubmitCalled: json['broker_submit_called'] == true,
      manualSubmitCalled: json['manual_submit_called'] == true,
    );
  }

  final DateTime? timestamp;
  final String eventType;
  final String title;
  final String? status;
  final String? source;
  final String? relatedId;
  final String? summary;
  final List<String> safetyFlags;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
}

String _string(Object? value, String fallback) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty || text == 'null' ? fallback : text;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty || text == 'null' ? null : text;
}

int _int(Object? value) => _nullableInt(value) ?? 0;

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim();
  if (text.isEmpty || text == 'null') return null;
  return int.tryParse(text);
}

double _double(Object? value) => _nullableDouble(value) ?? 0;

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}

DateTime? _nullableDateTime(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return DateTime.tryParse(text);
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item?.toString().trim().isNotEmpty == true) item.toString().trim(),
  ];
}

Map<String, dynamic> _map(Object? value) {
  return value is Map ? Map<String, dynamic>.from(value) : const {};
}
