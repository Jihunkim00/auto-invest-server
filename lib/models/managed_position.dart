class KisManagedPositions {
  const KisManagedPositions({
    required this.provider,
    required this.market,
    required this.positions,
    required this.rawPayload,
  });

  factory KisManagedPositions.fromJson(Map<String, dynamic> json) {
    final rawPositions = json['positions'] as List<dynamic>? ?? const [];
    return KisManagedPositions(
      provider: _readString(json['provider'], 'kis'),
      market: _readString(json['market'], 'KR'),
      positions: rawPositions
          .whereType<Map>()
          .map((item) => ManagedPosition.fromJson(
              Map<String, dynamic>.from(item.cast<String, dynamic>())))
          .toList(),
      rawPayload: Map<String, dynamic>.from(json),
    );
  }

  final String provider;
  final String market;
  final List<ManagedPosition> positions;
  final Map<String, dynamic> rawPayload;
}

class ManagedPosition {
  const ManagedPosition({
    required this.provider,
    required this.market,
    required this.symbol,
    required this.companyName,
    required this.quantity,
    this.averagePrice,
    this.costBasis,
    this.currentPrice,
    this.currentValue,
    this.unrealizedPl,
    this.unrealizedPlPct,
    required this.holdingStatus,
    required this.exitReason,
    required this.humanReason,
    required this.stopLossTriggered,
    required this.takeProfitTriggered,
    required this.weakTrendTriggered,
    required this.sellPressureTriggered,
    required this.manualReviewRequired,
    this.finalSellScore,
    this.finalBuyScore,
    this.quantSellScore,
    this.quantBuyScore,
    this.aiSellScore,
    this.aiBuyScore,
    this.confidence,
    required this.technicalSnapshot,
    required this.riskFlags,
    required this.gatingNotes,
    required this.blockReasons,
    required this.canPrepareManualSell,
    required this.canSubmitManualSell,
    this.latestManualSellOrder,
    required this.rawPayload,
  });

  factory ManagedPosition.fromJson(Map<String, dynamic> json) {
    return ManagedPosition(
      provider: _readString(json['provider'], 'kis'),
      market: _readString(json['market'], 'KR'),
      symbol: _readString(json['symbol'], ''),
      companyName: _companyName(json),
      quantity: _readDouble(json['quantity'] ?? json['qty']),
      averagePrice:
          _readNullableDouble(json['average_price'] ?? json['avg_entry_price']),
      costBasis: _readNullableDouble(json['cost_basis']),
      currentPrice: _readNullableDouble(json['current_price']),
      currentValue:
          _readNullableDouble(json['current_value'] ?? json['market_value']),
      unrealizedPl: _readNullableDouble(json['unrealized_pl']),
      unrealizedPlPct: _readNullableDouble(json['unrealized_pl_pct']),
      holdingStatus: _normalizeStatus(json['holding_status'] ?? json['status']),
      exitReason: _readString(json['exit_reason'], 'no_exit_condition'),
      humanReason:
          _readString(json['human_reason'], 'No sell trigger detected.'),
      stopLossTriggered: json['stop_loss_triggered'] == true,
      takeProfitTriggered: json['take_profit_triggered'] == true,
      weakTrendTriggered: json['weak_trend_triggered'] == true,
      sellPressureTriggered: json['sell_pressure_triggered'] == true,
      manualReviewRequired: json['manual_review_required'] == true,
      finalSellScore: _readNullableDouble(json['final_sell_score']),
      finalBuyScore: _readNullableDouble(json['final_buy_score']),
      quantSellScore: _readNullableDouble(json['quant_sell_score']),
      quantBuyScore: _readNullableDouble(json['quant_buy_score']),
      aiSellScore:
          _readNullableDouble(json['ai_sell_score'] ?? json['gpt_sell_score']),
      aiBuyScore:
          _readNullableDouble(json['ai_buy_score'] ?? json['gpt_buy_score']),
      confidence: _readNullableDouble(json['confidence']),
      technicalSnapshot: Map<String, dynamic>.from(
          (json['technical_snapshot'] as Map?) ?? const {}),
      riskFlags: _readStringList(json['risk_flags']),
      gatingNotes: _readStringList(json['gating_notes']),
      blockReasons: _readStringList(json['block_reasons']),
      canPrepareManualSell: json['can_prepare_manual_sell'] == true,
      canSubmitManualSell: json['can_submit_manual_sell'] == true,
      latestManualSellOrder:
          (json['latest_related_manual_sell_order'] as Map?) == null
              ? null
              : Map<String, dynamic>.from(
                  (json['latest_related_manual_sell_order'] as Map)
                      .cast<String, dynamic>()),
      rawPayload: Map<String, dynamic>.from(json),
    );
  }

  final String provider;
  final String market;
  final String symbol;
  final String companyName;
  final double quantity;
  final double? averagePrice;
  final double? costBasis;
  final double? currentPrice;
  final double? currentValue;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final String holdingStatus;
  final String exitReason;
  final String humanReason;
  final bool stopLossTriggered;
  final bool takeProfitTriggered;
  final bool weakTrendTriggered;
  final bool sellPressureTriggered;
  final bool manualReviewRequired;
  final double? finalSellScore;
  final double? finalBuyScore;
  final double? quantSellScore;
  final double? quantBuyScore;
  final double? aiSellScore;
  final double? aiBuyScore;
  final double? confidence;
  final Map<String, dynamic> technicalSnapshot;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<String> blockReasons;
  final bool canPrepareManualSell;
  final bool canSubmitManualSell;
  final Map<String, dynamic>? latestManualSellOrder;
  final Map<String, dynamic> rawPayload;

  bool get isHold => holdingStatus == 'HOLD';
  bool get isReviewSell => holdingStatus == 'REVIEW_SELL';
  bool get isSellReady => holdingStatus == 'SELL_READY';

  String get statusLabel => holdingStatus.replaceAll('_', ' ');
}

class ManualSellPreparation {
  const ManualSellPreparation({
    required this.provider,
    required this.market,
    required this.symbol,
    required this.companyName,
    required this.quantity,
    this.currentPrice,
    this.estimatedAmount,
    required this.exitReason,
    required this.humanReason,
    required this.holdingStatus,
    required this.canPrepare,
    required this.canSubmit,
    required this.blockReasons,
    required this.sourceMetadata,
    required this.rawPayload,
  });

  factory ManualSellPreparation.fromJson(Map<String, dynamic> json) {
    return ManualSellPreparation(
      provider: _readString(json['provider'], 'kis'),
      market: _readString(json['market'], 'KR'),
      symbol: _readString(json['symbol'], ''),
      companyName: _companyName(json),
      quantity: _readDouble(json['suggested_quantity'] ?? json['quantity']),
      currentPrice: _readNullableDouble(json['current_price']),
      estimatedAmount: _readNullableDouble(json['estimated_amount']),
      exitReason: _readString(json['exit_reason'], 'manual_review_required'),
      humanReason:
          _readString(json['human_reason'], 'Manual sell review prepared.'),
      holdingStatus: _normalizeStatus(json['holding_status']),
      canPrepare: json['can_prepare'] == true ||
          json['can_prepare_manual_sell'] == true,
      canSubmit:
          json['can_submit'] == true || json['can_submit_manual_sell'] == true,
      blockReasons: _readStringList(json['block_reasons']),
      sourceMetadata:
          Map<String, dynamic>.from((json['source_metadata'] as Map?) ?? {}),
      rawPayload: Map<String, dynamic>.from(json),
    );
  }

  final String provider;
  final String market;
  final String symbol;
  final String companyName;
  final double quantity;
  final double? currentPrice;
  final double? estimatedAmount;
  final String exitReason;
  final String humanReason;
  final String holdingStatus;
  final bool canPrepare;
  final bool canSubmit;
  final List<String> blockReasons;
  final Map<String, dynamic> sourceMetadata;
  final Map<String, dynamic> rawPayload;
}

String _companyName(Map<String, dynamic> json) {
  const keys = [
    'company_name',
    'name',
    'display_name',
    'symbol_name',
    'korean_name',
    'asset_name',
  ];
  for (final key in keys) {
    final value = _readString(json[key], '');
    if (value.isNotEmpty) return value;
  }
  return 'Unknown company';
}

String _normalizeStatus(Object? value) {
  final text = _readString(value, 'HOLD').trim().toUpperCase();
  if (text == 'SELL READY' || text == 'SELL_READY') return 'SELL_READY';
  if (text == 'REVIEW SELL' || text == 'REVIEW_SELL') return 'REVIEW_SELL';
  return 'HOLD';
}

double _readDouble(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString().replaceAll(',', '') ?? '') ?? 0;
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}

String _readString(Object? value, String fallback) {
  final text = value?.toString();
  if (text == null || text.trim().isEmpty || text == 'null') return fallback;
  return text;
}

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}
