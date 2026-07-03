class PositionExitReview {
  const PositionExitReview({
    required this.provider,
    required this.market,
    required this.positions,
    required this.totalPositionValue,
    required this.totalUnrealizedPl,
    this.totalUnrealizedPlPct,
    this.updatedAt,
    required this.safety,
    required this.safetyFlags,
  });

  factory PositionExitReview.fromJson(Map<String, dynamic> json) {
    final rawPositions = json['positions'];
    return PositionExitReview(
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      positions: rawPositions is List
          ? [
              for (final item in rawPositions)
                if (item is Map)
                  PositionExitReviewItem.fromJson(
                    Map<String, dynamic>.from(item),
                  ),
            ]
          : const [],
      totalPositionValue: _double(json['total_position_value']),
      totalUnrealizedPl: _double(json['total_unrealized_pl']),
      totalUnrealizedPlPct: _nullableDouble(json['total_unrealized_pl_pct']),
      updatedAt: _nullableDateTime(json['updated_at']),
      safety: _map(json['safety']),
      safetyFlags: _strings(json['safety_flags']),
    );
  }

  final String provider;
  final String market;
  final List<PositionExitReviewItem> positions;
  final double totalPositionValue;
  final double totalUnrealizedPl;
  final double? totalUnrealizedPlPct;
  final DateTime? updatedAt;
  final Map<String, dynamic> safety;
  final List<String> safetyFlags;
}

class PositionExitReviewItem {
  const PositionExitReviewItem({
    required this.symbol,
    this.name,
    required this.provider,
    required this.market,
    required this.quantity,
    required this.availableQuantity,
    this.averagePrice,
    this.costBasis,
    this.currentPrice,
    this.currentValue,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.dayPl,
    this.entrySource,
    this.relatedBuyOrderId,
    this.relatedPromotionId,
    this.stopLossThresholdPct,
    this.takeProfitThresholdPct,
    required this.stopLossTriggered,
    required this.takeProfitTriggered,
    required this.exitReviewStatus,
    required this.primaryRiskNote,
    required this.riskFlags,
    required this.gatingNotes,
    required this.nextSafeAction,
    required this.rawPayload,
  });

  factory PositionExitReviewItem.fromJson(Map<String, dynamic> json) {
    return PositionExitReviewItem(
      symbol: _string(json['symbol'], ''),
      name: _nullableString(json['name']),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      quantity: _double(json['quantity']),
      availableQuantity: _double(json['available_quantity']),
      averagePrice: _nullableDouble(json['average_price']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentPrice: _nullableDouble(json['current_price']),
      currentValue: _nullableDouble(json['current_value']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      dayPl: _nullableDouble(json['day_pl']),
      entrySource: _nullableString(json['entry_source']),
      relatedBuyOrderId: _nullableInt(json['related_buy_order_id']),
      relatedPromotionId: _nullableInt(json['related_promotion_id']),
      stopLossThresholdPct: _nullableDouble(json['stop_loss_threshold_pct']),
      takeProfitThresholdPct:
          _nullableDouble(json['take_profit_threshold_pct']),
      stopLossTriggered: json['stop_loss_triggered'] == true,
      takeProfitTriggered: json['take_profit_triggered'] == true,
      exitReviewStatus: _string(json['exit_review_status'], 'hold'),
      primaryRiskNote: _string(json['primary_risk_note'], ''),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      nextSafeAction: _string(json['next_safe_action'], 'monitor'),
      rawPayload: Map<String, dynamic>.from(json),
    );
  }

  final String symbol;
  final String? name;
  final String provider;
  final String market;
  final double quantity;
  final double availableQuantity;
  final double? averagePrice;
  final double? costBasis;
  final double? currentPrice;
  final double? currentValue;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final double? dayPl;
  final String? entrySource;
  final int? relatedBuyOrderId;
  final int? relatedPromotionId;
  final double? stopLossThresholdPct;
  final double? takeProfitThresholdPct;
  final bool stopLossTriggered;
  final bool takeProfitTriggered;
  final String exitReviewStatus;
  final String primaryRiskNote;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final String nextSafeAction;
  final Map<String, dynamic> rawPayload;

  String get displayName {
    final text = name?.trim() ?? '';
    return text.isEmpty ? symbol : '$symbol $text';
  }
}

class PositionSellPreflightResult {
  const PositionSellPreflightResult({
    required this.symbol,
    required this.provider,
    required this.market,
    required this.preflightStatus,
    required this.canSubmitAfterConfirmation,
    required this.finalConfirmationRequired,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    required this.positionExists,
    this.quantityHeld,
    this.availableQuantity,
    this.requestedQuantity,
    this.estimatedSellNotional,
    this.currentPrice,
    this.averagePrice,
    this.costBasis,
    this.currentValue,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.stopLossThresholdPct,
    this.takeProfitThresholdPct,
    required this.stopLossTriggered,
    required this.takeProfitTriggered,
    required this.killSwitch,
    required this.dryRun,
    required this.kisRealOrderEnabled,
    required this.marketSessionAllowed,
    required this.noNewEntryWindowAllowed,
    required this.riskFlags,
    required this.gatingNotes,
    required this.checklist,
    this.primaryBlockReason,
    required this.nextRequiredAction,
    required this.safety,
  });

  factory PositionSellPreflightResult.fromJson(Map<String, dynamic> json) {
    final rawChecklist = json['checklist'];
    return PositionSellPreflightResult(
      symbol: _string(json['symbol'], ''),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      preflightStatus: _string(json['preflight_status'], 'blocked'),
      canSubmitAfterConfirmation: json['can_submit_after_confirmation'] == true,
      finalConfirmationRequired: json['final_confirmation_required'] != false,
      realOrderSubmitted: json['real_order_submitted'] == true,
      brokerSubmitCalled: json['broker_submit_called'] == true,
      manualSubmitCalled: json['manual_submit_called'] == true,
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      positionExists: json['position_exists'] == true,
      quantityHeld: _nullableDouble(json['quantity_held']),
      availableQuantity: _nullableDouble(json['available_quantity']),
      requestedQuantity: _nullableDouble(json['requested_quantity']),
      estimatedSellNotional: _nullableDouble(json['estimated_sell_notional']),
      currentPrice: _nullableDouble(json['current_price']),
      averagePrice: _nullableDouble(json['average_price']),
      costBasis: _nullableDouble(json['cost_basis']),
      currentValue: _nullableDouble(json['current_value']),
      unrealizedPl: _nullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _nullableDouble(json['unrealized_pl_pct']),
      stopLossThresholdPct: _nullableDouble(json['stop_loss_threshold_pct']),
      takeProfitThresholdPct:
          _nullableDouble(json['take_profit_threshold_pct']),
      stopLossTriggered: json['stop_loss_triggered'] == true,
      takeProfitTriggered: json['take_profit_triggered'] == true,
      killSwitch: json['kill_switch'] == true,
      dryRun: json['dry_run'] == true,
      kisRealOrderEnabled: json['kis_real_order_enabled'] == true,
      marketSessionAllowed: json['market_session_allowed'] == true,
      noNewEntryWindowAllowed: json['no_new_entry_window_allowed'] == true,
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      checklist: rawChecklist is List
          ? [
              for (final item in rawChecklist)
                PositionSellPreflightChecklistItem.fromJson(item),
            ]
          : const [],
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      nextRequiredAction:
          _string(json['next_required_action'], 'manual_review_required'),
      safety: _map(json['safety']),
    );
  }

  final String symbol;
  final String provider;
  final String market;
  final String preflightStatus;
  final bool canSubmitAfterConfirmation;
  final bool finalConfirmationRequired;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final bool positionExists;
  final double? quantityHeld;
  final double? availableQuantity;
  final double? requestedQuantity;
  final double? estimatedSellNotional;
  final double? currentPrice;
  final double? averagePrice;
  final double? costBasis;
  final double? currentValue;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final double? stopLossThresholdPct;
  final double? takeProfitThresholdPct;
  final bool stopLossTriggered;
  final bool takeProfitTriggered;
  final bool killSwitch;
  final bool dryRun;
  final bool kisRealOrderEnabled;
  final bool marketSessionAllowed;
  final bool noNewEntryWindowAllowed;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<PositionSellPreflightChecklistItem> checklist;
  final String? primaryBlockReason;
  final String nextRequiredAction;
  final Map<String, dynamic> safety;

  bool get isAllowed => preflightStatus == 'allowed';
  bool get isBlocked => preflightStatus == 'blocked';
  bool get requiresReview => preflightStatus == 'review_required';
  bool get isReadOnly =>
      realOrderSubmitted == false &&
      brokerSubmitCalled == false &&
      manualSubmitCalled == false;
}

class PositionSellPreflightChecklistItem {
  const PositionSellPreflightChecklistItem({
    required this.key,
    required this.status,
    this.labelKey,
    this.displayLabel,
    this.detail,
    required this.blocking,
  });

  factory PositionSellPreflightChecklistItem.fromJson(Object? value) {
    if (value is Map) {
      final json = Map<String, dynamic>.from(value);
      return PositionSellPreflightChecklistItem(
        key: _string(json['key'], 'check'),
        status: _string(json['status'], 'warn'),
        labelKey: _nullableString(json['label_key']),
        displayLabel: _nullableString(json['display_label']),
        detail: _nullableString(json['detail']),
        blocking: json['blocking'] == true,
      );
    }
    return PositionSellPreflightChecklistItem(
      key: 'check',
      status: 'warn',
      detail: _nullableString(value),
      blocking: false,
    );
  }

  final String key;
  final String status;
  final String? labelKey;
  final String? displayLabel;
  final String? detail;
  final bool blocking;
}

String _string(Object? value, String fallback) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty || text == 'null' ? fallback : text;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty || text == 'null' ? null : text;
}

double _double(Object? value) => _nullableDouble(value) ?? 0;

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim();
  if (text.isEmpty || text == 'null') return null;
  return int.tryParse(text);
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
