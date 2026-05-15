import 'gpt_risk_context.dart';

class TradingLogItem {
  const TradingLogItem({
    required this.id,
    required this.runKey,
    required this.symbol,
    required this.triggerSource,
    required this.mode,
    required this.action,
    required this.result,
    required this.reason,
    required this.relatedOrderId,
    required this.createdAt,
    required this.gateLevel,
    this.provider = 'alpaca',
    this.market = 'US',
    this.stage = '',
    this.symbolRole,
    this.parentRunKey,
    this.signalId,
    this.dryRun,
    this.simulated = false,
    this.previewOnly = false,
    this.realOrderSubmitted,
    this.brokerSubmitCalled,
    this.manualSubmitCalled,
    this.source = '',
    this.sourceType,
    this.exitTrigger,
    this.exitTriggerSource,
    this.suggestedQuantity,
    this.costBasis,
    this.currentValue,
    this.currentPrice,
    this.unrealizedPl,
    this.unrealizedPlPct,
    this.filledQuantity,
    this.remainingQuantity,
    this.averageFillPrice,
    this.rejectedReason,
    this.lastSyncedAt,
    this.manualConfirmRequired,
    this.autoSellEnabled,
    this.schedulerRealOrderEnabled,
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.gptContext = GptRiskContext.empty,
  });

  final int id;
  final String runKey;
  final String provider;
  final String market;
  final String symbol;
  final String triggerSource;
  final String mode;
  final String action;
  final String result;
  final String reason;
  final String? relatedOrderId;
  final String? signalId;
  final String createdAt;
  final int gateLevel;
  final String stage;
  final String? symbolRole;
  final String? parentRunKey;
  final bool? dryRun;
  final bool simulated;
  final bool previewOnly;
  final bool? realOrderSubmitted;
  final bool? brokerSubmitCalled;
  final bool? manualSubmitCalled;
  final String source;
  final String? sourceType;
  final String? exitTrigger;
  final String? exitTriggerSource;
  final double? suggestedQuantity;
  final double? costBasis;
  final double? currentValue;
  final double? currentPrice;
  final double? unrealizedPl;
  final double? unrealizedPlPct;
  final double? filledQuantity;
  final double? remainingQuantity;
  final double? averageFillPrice;
  final String? rejectedReason;
  final String? lastSyncedAt;
  final bool? manualConfirmRequired;
  final bool? autoSellEnabled;
  final bool? schedulerRealOrderEnabled;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final GptRiskContext gptContext;

  bool get hasOrder => relatedOrderId != null;
  bool get isHold => action.toLowerCase() == 'hold';
  bool get isKis => _isKis(provider, market, mode, triggerSource);
  bool get isKisPreview =>
      _isKisPreview(provider, market, mode, triggerSource, result, previewOnly);
  bool get isKisDryRunAuto =>
      !isKisExitShadow &&
      _isKisDryRunAuto(
        provider,
        market,
        mode,
        triggerSource,
        simulated,
        result,
      );
  bool get isKisPreflight =>
      _isKisPreflight(provider, market, mode, triggerSource, result);
  bool get isKisExitShadow => _isKisExitShadow(
        provider,
        market,
        mode,
        triggerSource,
        source,
        sourceType,
      );
  bool get isKisManualLive =>
      isKis &&
      !isKisPreview &&
      !isKisDryRunAuto &&
      !isKisPreflight &&
      !isKisExitShadow;
  String get sourceLabel {
    if (isKisExitShadow) return 'KIS SHADOW EXIT';
    return _sourceLabel(
      provider: provider,
      market: market,
      mode: mode,
      triggerSource: triggerSource,
      result: result,
      simulated: simulated,
      previewOnly: previewOnly,
    );
  }

  List<String> get safetyBadges {
    final labels = _safetyBadges(
      provider: provider,
      market: market,
      mode: mode,
      triggerSource: triggerSource,
      result: result,
      simulated: simulated,
      previewOnly: previewOnly,
      realOrderSubmitted: realOrderSubmitted,
      brokerSubmitCalled: brokerSubmitCalled,
      manualSubmitCalled: manualSubmitCalled,
    );
    if (source == 'kis_live_exit_preflight') {
      _addUnique(labels, 'EXIT PREFLIGHT');
      _addUnique(labels, 'PREFLIGHT ONLY');
      _addUnique(labels, 'NO AUTO SELL');
      _addUnique(labels, 'NO BROKER SUBMIT');
    }
    if (isKisExitShadow) {
      _addUnique(labels, 'SHADOW EXIT');
      _addUnique(labels, 'DRY RUN');
      _addUnique(labels, 'DRY RUN SELL SIMULATION');
      _addUnique(
          labels,
          result.toLowerCase() == 'would_sell'
              ? 'WOULD SELL'
              : action.toLowerCase() == 'hold'
                  ? 'HOLD'
                  : action.toUpperCase());
      _addUnique(labels, 'NO BROKER SUBMIT');
      _addUnique(labels, 'NO MANUAL SUBMIT');
      _addUnique(labels, 'LIVE AUTO SELL DISABLED');
    }
    if (manualConfirmRequired == true) {
      _addUnique(labels, 'MANUAL CONFIRMATION REQUIRED');
    }
    if (schedulerRealOrderEnabled == false) {
      _addUnique(labels, 'SCHEDULER REAL ORDERS DISABLED');
    }
    return labels;
  }

  String get orderLabel => hasOrder ? relatedOrderId! : 'No order';
  String get statusLine {
    final actionText = action.isEmpty ? 'HOLD' : action.toUpperCase();
    if (!hasOrder && isHold) return '$actionText | No order';
    if (!hasOrder) return '${result.toUpperCase()} | No order';
    return '$actionText | Order $relatedOrderId';
  }

  factory TradingLogItem.fromJson(Map<String, dynamic> json) {
    return TradingLogItem(
      id: _intValue(json['id'] ?? json['run_id']),
      runKey: _stringValue(json['run_key'], fallback: 'run-${json['id']}'),
      provider: _stringValue(json['provider'] ?? json['broker'],
          fallback: _inferProviderFromJson(json)),
      market:
          _stringValue(json['market'], fallback: _inferMarketFromJson(json)),
      symbol: _stringValue(json['symbol'], fallback: 'UNKNOWN'),
      triggerSource: _stringValue(json['trigger_source'], fallback: 'manual'),
      mode: _stringValue(json['mode'], fallback: 'single_symbol'),
      action: _stringValue(json['action'], fallback: 'hold'),
      result: _stringValue(json['result'], fallback: 'skipped'),
      reason: _stringValue(json['reason'], fallback: ''),
      relatedOrderId:
          _nullableString(json['related_order_id'] ?? json['order_id']),
      signalId: _nullableString(json['signal_id']),
      createdAt: _stringValue(json['created_at'], fallback: ''),
      gateLevel: _intValue(json['gate_level']),
      stage: _stringValue(json['stage'], fallback: ''),
      symbolRole: _nullableString(json['symbol_role']),
      parentRunKey: _nullableString(json['parent_run_key']),
      dryRun: _boolValue(json['dry_run']),
      simulated: _boolValue(json['simulated']) ?? false,
      previewOnly: _boolValue(json['preview_only']) ?? false,
      realOrderSubmitted: _boolValue(json['real_order_submitted']),
      brokerSubmitCalled: _boolValue(json['broker_submit_called']),
      manualSubmitCalled: _boolValue(json['manual_submit_called']),
      source: _stringValue(json['source'], fallback: ''),
      sourceType: _nullableString(json['source_type']),
      exitTrigger: _nullableString(json['exit_trigger']),
      exitTriggerSource: _nullableString(
          json['exit_trigger_source'] ?? json['trigger_source']),
      suggestedQuantity: _doubleValue(json['suggested_quantity']),
      costBasis: _doubleValue(json['cost_basis']),
      currentValue: _doubleValue(json['current_value']),
      currentPrice: _doubleValue(json['current_price']),
      unrealizedPl: _doubleValue(json['unrealized_pl']),
      unrealizedPlPct: _doubleValue(json['unrealized_pl_pct']),
      filledQuantity:
          _doubleValue(json['filled_quantity'] ?? json['filled_qty']),
      remainingQuantity:
          _doubleValue(json['remaining_quantity'] ?? json['remaining_qty']),
      averageFillPrice:
          _doubleValue(json['average_fill_price'] ?? json['avg_fill_price']),
      rejectedReason: _nullableString(json['rejected_reason']),
      lastSyncedAt:
          _nullableString(json['last_synced_at'] ?? json['last_sync_at']),
      manualConfirmRequired: _boolValue(json['manual_confirm_required']),
      autoSellEnabled: _boolValue(json['auto_sell_enabled']),
      schedulerRealOrderEnabled:
          _boolValue(json['scheduler_real_order_enabled']),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      gptContext: GptRiskContext.fromJson(json['gpt_context']),
    );
  }
}

class OrderLogItem {
  const OrderLogItem({
    required this.id,
    required this.symbol,
    required this.side,
    required this.qty,
    required this.notional,
    required this.brokerOrderId,
    required this.brokerStatus,
    required this.internalStatus,
    required this.createdAt,
    required this.updatedAt,
    this.provider = 'alpaca',
    this.broker = 'alpaca',
    this.market = 'US',
    this.currency = 'USD',
    this.mode = 'manual_order',
    this.triggerSource = 'manual',
    this.action = '',
    this.result = '',
    this.reason = '',
    this.orderId,
    this.signalId,
    this.kisOdno,
    this.brokerOrderStatus,
    this.submittedAt,
    this.filledAt,
    this.dryRun,
    this.simulated = false,
    this.previewOnly = false,
    this.realOrderSubmitted,
    this.brokerSubmitCalled,
    this.manualSubmitCalled,
    this.source = '',
    this.sourceType,
    this.exitTrigger,
    this.exitTriggerSource,
    this.filledQuantity,
    this.remainingQuantity,
    this.averageFillPrice,
    this.rejectedReason,
    this.lastSyncedAt,
    this.manualConfirmRequired,
    this.autoSellEnabled,
    this.schedulerRealOrderEnabled,
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.gptContext = GptRiskContext.empty,
  });

  final int id;
  final int? orderId;
  final String provider;
  final String broker;
  final String market;
  final String currency;
  final String mode;
  final String triggerSource;
  final String symbol;
  final String side;
  final String action;
  final String result;
  final String reason;
  final double? qty;
  final double? notional;
  final String? brokerOrderId;
  final String? kisOdno;
  final String? brokerStatus;
  final String? brokerOrderStatus;
  final String internalStatus;
  final String? signalId;
  final String createdAt;
  final String updatedAt;
  final String? submittedAt;
  final String? filledAt;
  final bool? dryRun;
  final bool simulated;
  final bool previewOnly;
  final bool? realOrderSubmitted;
  final bool? brokerSubmitCalled;
  final bool? manualSubmitCalled;
  final String source;
  final String? sourceType;
  final String? exitTrigger;
  final String? exitTriggerSource;
  final double? filledQuantity;
  final double? remainingQuantity;
  final double? averageFillPrice;
  final String? rejectedReason;
  final String? lastSyncedAt;
  final bool? manualConfirmRequired;
  final bool? autoSellEnabled;
  final bool? schedulerRealOrderEnabled;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final GptRiskContext gptContext;

  String get statusLabel => brokerOrderStatus ?? brokerStatus ?? internalStatus;
  String get orderLabel => kisOdno ?? brokerOrderId ?? 'No broker order';
  bool get isKis => _isKis(provider, market, mode, triggerSource);
  bool get isKisPreview =>
      _isKisPreview(provider, market, mode, triggerSource, result, previewOnly);
  bool get isKisDryRunAuto => _isKisDryRunAuto(
        provider,
        market,
        mode,
        triggerSource,
        simulated || internalStatus.toUpperCase() == 'DRY_RUN_SIMULATED',
        result,
      );
  bool get isKisPreflight =>
      _isKisPreflight(provider, market, mode, triggerSource, result);
  bool get isKisManualLive =>
      isKis && !isKisPreview && !isKisDryRunAuto && !isKisPreflight;
  String get sourceLabel => _sourceLabel(
        provider: provider,
        market: market,
        mode: mode,
        triggerSource: triggerSource,
        result: result.isEmpty ? internalStatus : result,
        simulated:
            simulated || internalStatus.toUpperCase() == 'DRY_RUN_SIMULATED',
        previewOnly: previewOnly,
      );
  bool get isFromExitPreflight => source == 'kis_live_exit_preflight';
  List<String> get safetyBadges {
    final labels = _safetyBadges(
      provider: provider,
      market: market,
      mode: mode,
      triggerSource: triggerSource,
      result: result.isEmpty ? internalStatus : result,
      simulated:
          simulated || internalStatus.toUpperCase() == 'DRY_RUN_SIMULATED',
      previewOnly: previewOnly,
      realOrderSubmitted: realOrderSubmitted,
      brokerSubmitCalled: brokerSubmitCalled,
      manualSubmitCalled: manualSubmitCalled,
    );
    if (isFromExitPreflight) {
      _addUnique(labels, 'EXIT PREFLIGHT');
      _addUnique(labels, 'NO AUTO SELL');
      if (realOrderSubmitted != true &&
          brokerSubmitCalled != true &&
          manualSubmitCalled != true) {
        _addUnique(labels, 'PREFLIGHT ONLY');
        _addUnique(labels, 'NO BROKER SUBMIT');
      }
    }
    if (manualConfirmRequired == true) {
      _addUnique(labels, 'MANUAL CONFIRMATION REQUIRED');
    }
    if (schedulerRealOrderEnabled == false) {
      _addUnique(labels, 'SCHEDULER REAL ORDERS DISABLED');
    }
    if (manualSubmitCalled == true) {
      _addUnique(labels, 'MANUAL SUBMIT');
    }
    return labels;
  }

  factory OrderLogItem.fromJson(Map<String, dynamic> json) {
    final provider = _stringValue(
      json['provider'] ?? json['broker'],
      fallback: _inferProviderFromJson(json),
    );
    final market =
        _stringValue(json['market'], fallback: _inferMarketFromJson(json));
    final internalStatus =
        _stringValue(json['internal_status'], fallback: 'UNKNOWN');
    return OrderLogItem(
      id: _intValue(json['id'] ?? json['order_id']),
      orderId: _nullableInt(json['order_id']),
      provider: provider,
      broker: _stringValue(json['broker'], fallback: provider),
      market: market,
      currency: _stringValue(
        json['currency'],
        fallback: _inferCurrency(provider: provider, market: market),
      ),
      mode: _stringValue(json['mode'], fallback: 'manual_order'),
      triggerSource: _stringValue(json['trigger_source'], fallback: 'manual'),
      symbol: _stringValue(json['symbol'], fallback: 'UNKNOWN'),
      side: _stringValue(json['side'] ?? json['action'], fallback: 'buy'),
      action: _stringValue(json['action'] ?? json['side'], fallback: 'buy'),
      result: _stringValue(json['result'], fallback: internalStatus),
      reason: _stringValue(json['reason'], fallback: ''),
      qty: _doubleValue(json['qty'] ?? json['requested_qty']),
      notional: _doubleValue(json['notional']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      brokerStatus: _nullableString(json['broker_status']),
      brokerOrderStatus:
          _nullableString(json['broker_order_status'] ?? json['broker_status']),
      internalStatus: internalStatus,
      signalId: _nullableString(json['signal_id']),
      createdAt: _stringValue(json['created_at'], fallback: ''),
      updatedAt: _stringValue(json['updated_at'], fallback: ''),
      submittedAt: _nullableString(json['submitted_at']),
      filledAt: _nullableString(json['filled_at']),
      dryRun: _boolValue(json['dry_run']),
      simulated: _boolValue(json['simulated']) ??
          internalStatus.toUpperCase() == 'DRY_RUN_SIMULATED',
      previewOnly: _boolValue(json['preview_only']) ?? false,
      realOrderSubmitted: _boolValue(json['real_order_submitted']),
      brokerSubmitCalled: _boolValue(json['broker_submit_called']),
      manualSubmitCalled: _boolValue(json['manual_submit_called']),
      source: _stringValue(json['source'], fallback: ''),
      sourceType: _nullableString(json['source_type']),
      exitTrigger: _nullableString(json['exit_trigger']),
      exitTriggerSource: _nullableString(
          json['exit_trigger_source'] ?? json['trigger_source']),
      filledQuantity:
          _doubleValue(json['filled_quantity'] ?? json['filled_qty']),
      remainingQuantity:
          _doubleValue(json['remaining_quantity'] ?? json['remaining_qty']),
      averageFillPrice:
          _doubleValue(json['average_fill_price'] ?? json['avg_fill_price']),
      rejectedReason: _nullableString(json['rejected_reason']),
      lastSyncedAt:
          _nullableString(json['last_synced_at'] ?? json['last_sync_at']),
      manualConfirmRequired: _boolValue(json['manual_confirm_required']),
      autoSellEnabled: _boolValue(json['auto_sell_enabled']),
      schedulerRealOrderEnabled:
          _boolValue(json['scheduler_real_order_enabled']),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      gptContext: GptRiskContext.fromJson(json['gpt_context']),
    );
  }
}

class SignalLogItem {
  const SignalLogItem({
    required this.id,
    required this.runKey,
    required this.symbol,
    required this.action,
    required this.signalStatus,
    required this.buyScore,
    required this.sellScore,
    required this.confidence,
    required this.reason,
    required this.relatedOrderId,
    required this.createdAt,
    this.provider = 'alpaca',
    this.market = 'US',
    this.mode = 'signal',
    this.triggerSource = '',
    this.result = '',
    this.dryRun,
    this.simulated = false,
    this.previewOnly = false,
    this.realOrderSubmitted,
    this.brokerSubmitCalled,
    this.manualSubmitCalled,
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.gptContext = GptRiskContext.empty,
  });

  final int id;
  final String? runKey;
  final String provider;
  final String market;
  final String mode;
  final String triggerSource;
  final String symbol;
  final String action;
  final String signalStatus;
  final String result;
  final double? buyScore;
  final double? sellScore;
  final double? confidence;
  final String reason;
  final String? relatedOrderId;
  final String createdAt;
  final bool? dryRun;
  final bool simulated;
  final bool previewOnly;
  final bool? realOrderSubmitted;
  final bool? brokerSubmitCalled;
  final bool? manualSubmitCalled;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final GptRiskContext gptContext;

  bool get hasOrder => relatedOrderId != null;
  String get orderLabel => hasOrder ? relatedOrderId! : 'No order';
  String get statusLine =>
      '${action.toUpperCase()} | ${signalStatus.toUpperCase()}';
  bool get isKis => _isKis(provider, market, mode, triggerSource);
  bool get isKisPreview =>
      _isKisPreview(provider, market, mode, triggerSource, result, previewOnly);
  bool get isKisDryRunAuto => _isKisDryRunAuto(
        provider,
        market,
        mode,
        triggerSource,
        simulated,
        result,
      );
  bool get isKisPreflight =>
      _isKisPreflight(provider, market, mode, triggerSource, result);
  bool get isKisManualLive =>
      isKis && !isKisPreview && !isKisDryRunAuto && !isKisPreflight;
  String get sourceLabel => _sourceLabel(
        provider: provider,
        market: market,
        mode: mode,
        triggerSource: triggerSource,
        result: result.isEmpty ? signalStatus : result,
        simulated: simulated,
        previewOnly: previewOnly,
      );
  List<String> get safetyBadges => _safetyBadges(
        provider: provider,
        market: market,
        mode: mode,
        triggerSource: triggerSource,
        result: result.isEmpty ? signalStatus : result,
        simulated: simulated,
        previewOnly: previewOnly,
        realOrderSubmitted: realOrderSubmitted,
        brokerSubmitCalled: brokerSubmitCalled,
        manualSubmitCalled: manualSubmitCalled,
      );

  factory SignalLogItem.fromJson(Map<String, dynamic> json) {
    final status = _stringValue(json['signal_status'] ?? json['result'],
        fallback: 'skipped');
    return SignalLogItem(
      id: _intValue(json['id']),
      runKey: _nullableString(json['run_key']),
      provider: _stringValue(json['provider'] ?? json['broker'],
          fallback: _inferProviderFromJson(json)),
      market:
          _stringValue(json['market'], fallback: _inferMarketFromJson(json)),
      mode: _stringValue(json['mode'], fallback: 'signal'),
      triggerSource: _stringValue(json['trigger_source'], fallback: ''),
      symbol: _stringValue(json['symbol'], fallback: 'UNKNOWN'),
      action: _stringValue(json['action'], fallback: 'hold'),
      signalStatus: status,
      result: _stringValue(json['result'], fallback: status),
      buyScore: _doubleValue(json['buy_score']),
      sellScore: _doubleValue(json['sell_score']),
      confidence: _doubleValue(json['confidence']),
      reason: _stringValue(json['reason'], fallback: ''),
      relatedOrderId:
          _nullableString(json['related_order_id'] ?? json['order_id']),
      createdAt: _stringValue(json['created_at'], fallback: ''),
      dryRun: _boolValue(json['dry_run']),
      simulated: _boolValue(json['simulated']) ?? status == 'simulated',
      previewOnly: _boolValue(json['preview_only']) ?? false,
      realOrderSubmitted: _boolValue(json['real_order_submitted']),
      brokerSubmitCalled: _boolValue(json['broker_submit_called']),
      manualSubmitCalled: _boolValue(json['manual_submit_called']),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      gptContext: GptRiskContext.fromJson(json['gpt_context']),
    );
  }
}

class LogsSummary {
  const LogsSummary({
    required this.latestRun,
    required this.latestOrder,
    required this.latestSignal,
    required this.counts,
  });

  final TradingLogItem? latestRun;
  final OrderLogItem? latestOrder;
  final SignalLogItem? latestSignal;
  final Map<String, int> counts;

  factory LogsSummary.fromJson(Map<String, dynamic> json) {
    return LogsSummary(
      latestRun: _optionalMap(json['latest_run']) == null
          ? null
          : TradingLogItem.fromJson(_optionalMap(json['latest_run'])!),
      latestOrder: _optionalMap(json['latest_order']) == null
          ? null
          : OrderLogItem.fromJson(_optionalMap(json['latest_order'])!),
      latestSignal: _optionalMap(json['latest_signal']) == null
          ? null
          : SignalLogItem.fromJson(_optionalMap(json['latest_signal'])!),
      counts: _intMap(json['counts']),
    );
  }
}

Map<String, dynamic>? _optionalMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return null;
}

Map<String, int> _intMap(Object? value) {
  final map = <String, int>{};
  if (value is Map) {
    for (final entry in value.entries) {
      map[entry.key.toString()] = _intValue(entry.value);
    }
  }
  return map;
}

int _intValue(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim();
  if (text.isEmpty || text == 'null') return null;
  return int.tryParse(text);
}

double? _doubleValue(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString().replaceAll(',', '') ?? '');
}

String _stringValue(Object? value, {required String fallback}) {
  final text = value?.toString();
  if (text == null || text.isEmpty || text == 'null') return fallback;
  return text;
}

String? _nullableString(Object? value) {
  final text = value?.toString();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

bool? _boolValue(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

List<String> _stringList(Object? value) {
  if (value is List) {
    return value
        .map((item) => item.toString())
        .where((item) => item.trim().isNotEmpty)
        .toList();
  }
  return const [];
}

String _inferProviderFromJson(Map<String, dynamic> json) {
  final hint =
      '${json['mode'] ?? ''} ${json['trigger_source'] ?? ''} ${json['market'] ?? ''}'
          .toLowerCase();
  if (hint.contains('kis') || hint.contains('kr')) return 'kis';
  return 'alpaca';
}

String _inferMarketFromJson(Map<String, dynamic> json) {
  final market = json['market']?.toString().trim().toUpperCase();
  if (market != null && market.isNotEmpty && market != 'NULL') return market;
  return _inferProviderFromJson(json) == 'kis' ? 'KR' : 'US';
}

String _inferCurrency({required String provider, required String market}) {
  if (provider.trim().toLowerCase() == 'kis' ||
      market.trim().toUpperCase() == 'KR') {
    return 'KRW';
  }
  return 'USD';
}

bool _isKis(String provider, String market, String mode, String triggerSource) {
  return provider.trim().toLowerCase() == 'kis' ||
      market.trim().toUpperCase() == 'KR' ||
      mode.toLowerCase().contains('kis') ||
      triggerSource.toLowerCase().contains('kis');
}

bool _isKisPreview(
  String provider,
  String market,
  String mode,
  String triggerSource,
  String result,
  bool previewOnly,
) {
  if (!_isKis(provider, market, mode, triggerSource)) return false;
  return previewOnly ||
      mode.toLowerCase().contains('preview') ||
      triggerSource.toLowerCase().contains('preview') ||
      result.toLowerCase() == 'preview_only';
}

bool _isKisDryRunAuto(
  String provider,
  String market,
  String mode,
  String triggerSource,
  bool simulated,
  String result,
) {
  if (!_isKis(provider, market, mode, triggerSource)) return false;
  return simulated ||
      mode.toLowerCase().contains('dry_run_auto') ||
      triggerSource.toLowerCase().contains('dry_run_auto') ||
      result.toUpperCase() == 'DRY_RUN_SIMULATED';
}

bool _isKisPreflight(
  String provider,
  String market,
  String mode,
  String triggerSource,
  String result,
) {
  if (!_isKis(provider, market, mode, triggerSource)) return false;
  return mode.toLowerCase().contains('preflight') ||
      triggerSource.toLowerCase().contains('preflight') ||
      result.toLowerCase().contains('preflight');
}

bool _isKisExitShadow(
  String provider,
  String market,
  String mode,
  String triggerSource,
  String source,
  String? sourceType,
) {
  if (!_isKis(provider, market, mode, triggerSource)) return false;
  final hint = '$mode $triggerSource $source ${sourceType ?? ''}'.toLowerCase();
  return hint.contains('shadow_exit') ||
      hint.contains('exit_shadow') ||
      source == 'kis_exit_shadow_decision' ||
      sourceType == 'dry_run_sell_simulation';
}

String _sourceLabel({
  required String provider,
  required String market,
  required String mode,
  required String triggerSource,
  required String result,
  required bool simulated,
  required bool previewOnly,
}) {
  final kis = _isKis(provider, market, mode, triggerSource);
  if (!kis) return 'ALPACA PAPER';
  if (_isKisDryRunAuto(
      provider, market, mode, triggerSource, simulated, result)) {
    return 'KIS DRY-RUN AUTO';
  }
  if (_isKisPreflight(provider, market, mode, triggerSource, result)) {
    return 'KIS EXIT PREFLIGHT';
  }
  if (_isKisPreview(
      provider, market, mode, triggerSource, result, previewOnly)) {
    return 'KIS PREVIEW';
  }
  return 'KIS MANUAL LIVE';
}

List<String> _safetyBadges({
  required String provider,
  required String market,
  required String mode,
  required String triggerSource,
  required String result,
  required bool simulated,
  required bool previewOnly,
  required bool? realOrderSubmitted,
  required bool? brokerSubmitCalled,
  required bool? manualSubmitCalled,
}) {
  final labels = <String>[];
  final kis = _isKis(provider, market, mode, triggerSource);
  final preview = _isKisPreview(
    provider,
    market,
    mode,
    triggerSource,
    result,
    previewOnly,
  );
  final dryRunAuto = _isKisDryRunAuto(
    provider,
    market,
    mode,
    triggerSource,
    simulated,
    result,
  );
  final preflight =
      _isKisPreflight(provider, market, mode, triggerSource, result);
  void add(String label) {
    if (!labels.contains(label)) labels.add(label);
  }

  if (dryRunAuto || simulated) add('SIMULATED');
  if (preview || previewOnly) add('PREVIEW ONLY');
  if (preflight) add('PREFLIGHT ONLY');
  if (realOrderSubmitted == true) add('REAL ORDER SUBMITTED');
  if (kis &&
      (brokerSubmitCalled == false ||
          (realOrderSubmitted == false &&
              (dryRunAuto || preview || preflight)))) {
    add('NO BROKER SUBMIT');
  }
  if (kis && !dryRunAuto && !preview && !preflight) add('MANUAL ONLY');
  if (manualSubmitCalled == true) add('MANUAL ONLY');
  return labels;
}

void _addUnique(List<String> labels, String label) {
  if (!labels.contains(label)) labels.add(label);
}

const mockTradingLogManualHold = TradingLogItem(
  id: 1,
  runKey: 'mock-manual-hold',
  symbol: 'WMT',
  triggerSource: 'manual',
  mode: 'single_symbol',
  action: 'hold',
  result: 'skipped',
  reason: 'weak_final_score_gap',
  relatedOrderId: null,
  createdAt: '2026-04-26T12:20:00Z',
  gateLevel: 2,
);

const mockTradingLogSchedulerDisabled = TradingLogItem(
  id: 2,
  runKey: 'mock-scheduler-disabled',
  symbol: 'CSCO',
  triggerSource: 'scheduler',
  mode: 'watchlist',
  action: 'hold',
  result: 'skipped',
  reason: 'scheduler_disabled',
  relatedOrderId: null,
  createdAt: '2026-04-26T09:00:00Z',
  gateLevel: 2,
);

const mockTradingLogs = <TradingLogItem>[
  mockTradingLogManualHold,
  mockTradingLogSchedulerDisabled,
];

const mockOrderLogs = <OrderLogItem>[];

const mockSignalLogHold = SignalLogItem(
  id: 1,
  runKey: null,
  symbol: 'WMT',
  action: 'hold',
  signalStatus: 'skipped',
  buyScore: 42,
  sellScore: 21,
  confidence: 0.61,
  reason: 'hold_signal',
  relatedOrderId: null,
  createdAt: '2026-04-26T12:20:00Z',
);

const mockSignalLogs = <SignalLogItem>[
  mockSignalLogHold,
];

const mockLogsSummary = LogsSummary(
  latestRun: mockTradingLogManualHold,
  latestOrder: null,
  latestSignal: mockSignalLogHold,
  counts: {'runs': 2, 'orders': 0, 'signals': 1},
);
