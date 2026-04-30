class TradingRun {
  const TradingRun({
    required this.timestamp,
    required this.triggerSource,
    required this.symbol,
    required this.result,
    required this.reason,
    required this.bestScore,
    required this.orderId,
    required this.action,
    required this.gateLevel,
  });

  final String timestamp;
  final String triggerSource;
  final String symbol;
  final String result;
  final String reason;
  final int bestScore;
  final String? orderId;
  final String action;
  final int gateLevel;
}
