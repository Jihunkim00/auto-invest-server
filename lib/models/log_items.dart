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
  });

  final int id;
  final String runKey;
  final String symbol;
  final String triggerSource;
  final String mode;
  final String action;
  final String result;
  final String reason;
  final String? relatedOrderId;
  final String createdAt;
  final int gateLevel;

  bool get hasOrder => relatedOrderId != null;
  bool get isHold => action.toLowerCase() == 'hold';
  String get orderLabel => hasOrder ? relatedOrderId! : 'No order';
  String get statusLine {
    final actionText = action.isEmpty ? 'HOLD' : action.toUpperCase();
    if (!hasOrder && isHold) return '$actionText | No order';
    if (!hasOrder) return '${result.toUpperCase()} | No order';
    return '$actionText | Order $relatedOrderId';
  }

  factory TradingLogItem.fromJson(Map<String, dynamic> json) {
    return TradingLogItem(
      id: _intValue(json['id']),
      runKey: _stringValue(json['run_key'], fallback: 'run-${json['id']}'),
      symbol: _stringValue(json['symbol'], fallback: 'UNKNOWN'),
      triggerSource: _stringValue(json['trigger_source'], fallback: 'manual'),
      mode: _stringValue(json['mode'], fallback: 'single_symbol'),
      action: _stringValue(json['action'], fallback: 'hold'),
      result: _stringValue(json['result'], fallback: 'skipped'),
      reason: _stringValue(json['reason'], fallback: ''),
      relatedOrderId:
          _nullableString(json['related_order_id'] ?? json['order_id']),
      createdAt: _stringValue(json['created_at'], fallback: ''),
      gateLevel: _intValue(json['gate_level']),
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
  });

  final int id;
  final String symbol;
  final String side;
  final double? qty;
  final double? notional;
  final String? brokerOrderId;
  final String? brokerStatus;
  final String internalStatus;
  final String createdAt;
  final String updatedAt;

  String get statusLabel => brokerStatus ?? internalStatus;
  String get orderLabel => brokerOrderId ?? 'No broker order';

  factory OrderLogItem.fromJson(Map<String, dynamic> json) {
    return OrderLogItem(
      id: _intValue(json['id']),
      symbol: _stringValue(json['symbol'], fallback: 'UNKNOWN'),
      side: _stringValue(json['side'], fallback: 'buy'),
      qty: _doubleValue(json['qty']),
      notional: _doubleValue(json['notional']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      brokerStatus: _nullableString(json['broker_status']),
      internalStatus:
          _stringValue(json['internal_status'], fallback: 'UNKNOWN'),
      createdAt: _stringValue(json['created_at'], fallback: ''),
      updatedAt: _stringValue(json['updated_at'], fallback: ''),
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
  });

  final int id;
  final String? runKey;
  final String symbol;
  final String action;
  final String signalStatus;
  final double? buyScore;
  final double? sellScore;
  final double? confidence;
  final String reason;
  final String? relatedOrderId;
  final String createdAt;

  bool get hasOrder => relatedOrderId != null;
  String get orderLabel => hasOrder ? relatedOrderId! : 'No order';
  String get statusLine =>
      '${action.toUpperCase()} | ${signalStatus.toUpperCase()}';

  factory SignalLogItem.fromJson(Map<String, dynamic> json) {
    return SignalLogItem(
      id: _intValue(json['id']),
      runKey: _nullableString(json['run_key']),
      symbol: _stringValue(json['symbol'], fallback: 'UNKNOWN'),
      action: _stringValue(json['action'], fallback: 'hold'),
      signalStatus: _stringValue(json['signal_status'], fallback: 'skipped'),
      buyScore: _doubleValue(json['buy_score']),
      sellScore: _doubleValue(json['sell_score']),
      confidence: _doubleValue(json['confidence']),
      reason: _stringValue(json['reason'], fallback: ''),
      relatedOrderId: _nullableString(json['related_order_id']),
      createdAt: _stringValue(json['created_at'], fallback: ''),
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
  return null;
}

Map<String, int> _intMap(Object? value) {
  final map = <String, int>{};
  if (value is Map<String, dynamic>) {
    for (final entry in value.entries) {
      map[entry.key] = _intValue(entry.value);
    }
  }
  return map;
}

int _intValue(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

double? _doubleValue(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
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
