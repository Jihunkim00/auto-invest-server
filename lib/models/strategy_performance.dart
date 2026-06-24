import 'strategy_profile.dart';

class StrategyDataQuality {
  const StrategyDataQuality({
    required this.isEstimated,
    required this.hasCompleteFills,
    required this.missingCostBasis,
    required this.unmatchedOrdersCount,
    required this.notes,
    this.raw = const {},
  });

  final bool isEstimated;
  final bool hasCompleteFills;
  final bool missingCostBasis;
  final int unmatchedOrdersCount;
  final List<String> notes;
  final Map<String, dynamic> raw;

  bool get hasWarnings =>
      !hasCompleteFills ||
      missingCostBasis ||
      unmatchedOrdersCount > 0 ||
      notes.isNotEmpty;

  factory StrategyDataQuality.fromJson(Map<String, dynamic> json) {
    return StrategyDataQuality(
      isEstimated: json['is_estimated'] != false,
      hasCompleteFills: json['has_complete_fills'] == true,
      missingCostBasis: json['missing_cost_basis'] == true,
      unmatchedOrdersCount: _readInt(json['unmatched_orders_count']),
      notes: _readStringList(json['notes']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class StrategyDailyPerformance {
  const StrategyDailyPerformance({
    required this.date,
    required this.provider,
    required this.market,
    required this.activeProfile,
    required this.realizedPnl,
    required this.unrealizedPnl,
    required this.grossPnl,
    required this.estimatedFees,
    required this.netPnlEstimated,
    required this.pnlPct,
    required this.ordersCount,
    required this.filledOrdersCount,
    required this.rejectedOrdersCount,
    required this.winningTradesCount,
    required this.losingTradesCount,
    required this.winRate,
    required this.dataQuality,
    required this.safety,
  });

  final String date;
  final String provider;
  final String market;
  final StrategyProfile activeProfile;
  final double realizedPnl;
  final double unrealizedPnl;
  final double grossPnl;
  final double estimatedFees;
  final double netPnlEstimated;
  final double pnlPct;
  final int ordersCount;
  final int filledOrdersCount;
  final int rejectedOrdersCount;
  final int winningTradesCount;
  final int losingTradesCount;
  final double winRate;
  final StrategyDataQuality dataQuality;
  final Map<String, dynamic> safety;

  factory StrategyDailyPerformance.fromJson(Map<String, dynamic> json) {
    return StrategyDailyPerformance(
      date: _readString(json['date']),
      provider: _readString(json['provider'], 'kis'),
      market: _readString(json['market'], 'KR'),
      activeProfile: StrategyProfile.fromJson(_readMap(json['active_profile'])),
      realizedPnl: _readDouble(json['realized_pnl']),
      unrealizedPnl: _readDouble(json['unrealized_pnl']),
      grossPnl: _readDouble(json['gross_pnl']),
      estimatedFees: _readDouble(json['estimated_fees']),
      netPnlEstimated: _readDouble(json['net_pnl_estimated']),
      pnlPct: _readDouble(json['pnl_pct']),
      ordersCount: _readInt(json['orders_count']),
      filledOrdersCount: _readInt(json['filled_orders_count']),
      rejectedOrdersCount: _readInt(json['rejected_orders_count']),
      winningTradesCount: _readInt(json['winning_trades_count']),
      losingTradesCount: _readInt(json['losing_trades_count']),
      winRate: _readDouble(json['win_rate']),
      dataQuality: StrategyDataQuality.fromJson(_readMap(json['data_quality'])),
      safety: _readMap(json['safety']),
    );
  }
}

class StrategyMonthlyPerformance {
  const StrategyMonthlyPerformance({
    required this.month,
    required this.provider,
    required this.market,
    required this.activeProfile,
    required this.monthlyTargetReturnPct,
    required this.monthlyTargetMinPct,
    required this.monthlyTargetMaxPct,
    required this.currentMonthReturnPct,
    required this.targetProgressPct,
    required this.monthlyMaxLossPct,
    required this.lossBudgetUsedPct,
    required this.targetHit,
    required this.lossLimitHit,
    required this.realizedPnl,
    required this.unrealizedPnl,
    required this.grossPnl,
    required this.netPnlEstimated,
    required this.estimatedFees,
    required this.ordersCount,
    required this.filledOrdersCount,
    required this.rejectedOrdersCount,
    required this.winningTradesCount,
    required this.losingTradesCount,
    required this.winRate,
    required this.averageWin,
    required this.averageLoss,
    required this.maxDrawdownPct,
    required this.newEntriesAllowedByTarget,
    required this.dataQuality,
    required this.safety,
    this.profitFactor,
    this.newEntriesBlockReason,
  });

  final String month;
  final String provider;
  final String market;
  final StrategyProfile activeProfile;
  final double monthlyTargetReturnPct;
  final double monthlyTargetMinPct;
  final double monthlyTargetMaxPct;
  final double currentMonthReturnPct;
  final double targetProgressPct;
  final double monthlyMaxLossPct;
  final double lossBudgetUsedPct;
  final bool targetHit;
  final bool lossLimitHit;
  final double realizedPnl;
  final double unrealizedPnl;
  final double grossPnl;
  final double netPnlEstimated;
  final double estimatedFees;
  final int ordersCount;
  final int filledOrdersCount;
  final int rejectedOrdersCount;
  final int winningTradesCount;
  final int losingTradesCount;
  final double winRate;
  final double averageWin;
  final double averageLoss;
  final double? profitFactor;
  final double maxDrawdownPct;
  final bool newEntriesAllowedByTarget;
  final String? newEntriesBlockReason;
  final StrategyDataQuality dataQuality;
  final Map<String, dynamic> safety;

  factory StrategyMonthlyPerformance.fromJson(Map<String, dynamic> json) {
    return StrategyMonthlyPerformance(
      month: _readString(json['month']),
      provider: _readString(json['provider'], 'kis'),
      market: _readString(json['market'], 'KR'),
      activeProfile: StrategyProfile.fromJson(_readMap(json['active_profile'])),
      monthlyTargetReturnPct: _readDouble(json['monthly_target_return_pct']),
      monthlyTargetMinPct: _readDouble(json['monthly_target_min_pct']),
      monthlyTargetMaxPct: _readDouble(json['monthly_target_max_pct']),
      currentMonthReturnPct: _readDouble(json['current_month_return_pct']),
      targetProgressPct: _readDouble(json['target_progress_pct']),
      monthlyMaxLossPct: _readDouble(json['monthly_max_loss_pct']),
      lossBudgetUsedPct: _readDouble(json['loss_budget_used_pct']),
      targetHit: json['target_hit'] == true,
      lossLimitHit: json['loss_limit_hit'] == true,
      realizedPnl: _readDouble(json['realized_pnl']),
      unrealizedPnl: _readDouble(json['unrealized_pnl']),
      grossPnl: _readDouble(json['gross_pnl']),
      netPnlEstimated: _readDouble(json['net_pnl_estimated']),
      estimatedFees: _readDouble(json['estimated_fees']),
      ordersCount: _readInt(json['orders_count']),
      filledOrdersCount: _readInt(json['filled_orders_count']),
      rejectedOrdersCount: _readInt(json['rejected_orders_count']),
      winningTradesCount: _readInt(json['winning_trades_count']),
      losingTradesCount: _readInt(json['losing_trades_count']),
      winRate: _readDouble(json['win_rate']),
      averageWin: _readDouble(json['average_win']),
      averageLoss: _readDouble(json['average_loss']),
      profitFactor: _readNullableDouble(json['profit_factor']),
      maxDrawdownPct: _readDouble(json['max_drawdown_pct']),
      newEntriesAllowedByTarget: json['new_entries_allowed_by_target'] != false,
      newEntriesBlockReason:
          _readNullableString(json['new_entries_block_reason']),
      dataQuality: StrategyDataQuality.fromJson(_readMap(json['data_quality'])),
      safety: _readMap(json['safety']),
    );
  }
}

class StrategyTradePerformanceItem {
  const StrategyTradePerformanceItem({
    required this.symbol,
    required this.provider,
    required this.market,
    required this.side,
    required this.quantity,
    required this.status,
    required this.riskFlags,
    required this.gatingNotes,
    required this.dataQuality,
    this.orderId,
    this.entryOrderId,
    this.exitOrderId,
    this.symbolName,
    this.entryPrice,
    this.exitPrice,
    this.currentPrice,
    this.realizedPnl,
    this.unrealizedPnl,
    this.netPnlEstimated,
    this.pnlPct,
    this.holdingMinutes,
    this.decisionSource,
    this.signalId,
    this.runId,
    this.agentChatActionId,
    this.createdAt,
    this.closedAt,
  });

  final int? orderId;
  final int? entryOrderId;
  final int? exitOrderId;
  final String symbol;
  final String? symbolName;
  final String provider;
  final String market;
  final String side;
  final double quantity;
  final double? entryPrice;
  final double? exitPrice;
  final double? currentPrice;
  final double? realizedPnl;
  final double? unrealizedPnl;
  final double? netPnlEstimated;
  final double? pnlPct;
  final int? holdingMinutes;
  final String? decisionSource;
  final int? signalId;
  final int? runId;
  final int? agentChatActionId;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final String? createdAt;
  final String? closedAt;
  final String status;
  final StrategyDataQuality dataQuality;

  double? get displayPnl => realizedPnl ?? unrealizedPnl ?? netPnlEstimated;

  factory StrategyTradePerformanceItem.fromJson(Map<String, dynamic> json) {
    return StrategyTradePerformanceItem(
      orderId: _readNullableInt(json['order_id']),
      entryOrderId: _readNullableInt(json['entry_order_id']),
      exitOrderId: _readNullableInt(json['exit_order_id']),
      symbol: _readString(json['symbol']),
      symbolName: _readNullableString(json['symbol_name']),
      provider: _readString(json['provider'], 'kis'),
      market: _readString(json['market'], 'KR'),
      side: _readString(json['side']),
      quantity: _readDouble(json['quantity']),
      entryPrice: _readNullableDouble(json['entry_price']),
      exitPrice: _readNullableDouble(json['exit_price']),
      currentPrice: _readNullableDouble(json['current_price']),
      realizedPnl: _readNullableDouble(json['realized_pnl']),
      unrealizedPnl: _readNullableDouble(json['unrealized_pnl']),
      netPnlEstimated: _readNullableDouble(json['net_pnl_estimated']),
      pnlPct: _readNullableDouble(json['pnl_pct']),
      holdingMinutes: _readNullableInt(json['holding_minutes']),
      decisionSource: _readNullableString(json['decision_source']),
      signalId: _readNullableInt(json['signal_id']),
      runId: _readNullableInt(json['run_id']),
      agentChatActionId: _readNullableInt(json['agent_chat_action_id']),
      riskFlags: _readStringList(json['risk_flags']),
      gatingNotes: _readStringList(json['gating_notes']),
      createdAt: _readNullableString(json['created_at']),
      closedAt: _readNullableString(json['closed_at']),
      status: _readString(json['status']),
      dataQuality: StrategyDataQuality.fromJson(_readMap(json['data_quality'])),
    );
  }
}

class StrategyTradePerformanceList {
  const StrategyTradePerformanceList({
    required this.provider,
    required this.market,
    required this.count,
    required this.items,
    required this.dataQuality,
    required this.safety,
  });

  final String provider;
  final String market;
  final int count;
  final List<StrategyTradePerformanceItem> items;
  final StrategyDataQuality dataQuality;
  final Map<String, dynamic> safety;

  factory StrategyTradePerformanceList.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'] as List<dynamic>? ?? const [];
    return StrategyTradePerformanceList(
      provider: _readString(json['provider'], 'kis'),
      market: _readString(json['market'], 'KR'),
      count: _readInt(json['count']),
      items: [
        for (final item in rawItems)
          if (item is Map)
            StrategyTradePerformanceItem.fromJson(
              Map<String, dynamic>.from(item),
            ),
      ],
      dataQuality: StrategyDataQuality.fromJson(_readMap(json['data_quality'])),
      safety: _readMap(json['safety']),
    );
  }
}

Map<String, dynamic> _readMap(Object? value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

String _readString(Object? value, [String fallback = '']) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? fallback : text;
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

double _readDouble(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? 0;
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString());
}

int _readInt(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item?.toString().trim().isNotEmpty == true) item.toString().trim(),
  ];
}
