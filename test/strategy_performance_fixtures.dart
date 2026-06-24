Map<String, dynamic> strategyProfileJson() {
  return {
    'id': 2,
    'profile_name': 'balanced',
    'display_name': 'Balanced',
    'description': 'Balanced test profile',
    'monthly_target_return_pct': 0.04,
    'monthly_target_min_pct': 0.03,
    'monthly_target_max_pct': 0.05,
    'monthly_max_loss_pct': -0.04,
    'daily_max_loss_pct': -0.01,
    'max_order_notional_pct': 0.04,
    'max_order_notional_krw': 50000,
    'max_trades_per_day': 1,
    'max_positions': 3,
    'buy_score_threshold': 68,
    'sell_score_threshold': 60,
    'stop_loss_pct': -0.02,
    'take_profit_pct': 0.04,
    'max_holding_days': 7,
    'stop_after_monthly_target': true,
    'reduce_size_after_loss': true,
    'consecutive_loss_reduce_threshold': 2,
    'is_active': true,
    'is_builtin': true,
  };
}

Map<String, dynamic> strategyDataQualityJson({
  bool hasCompleteFills = true,
  bool missingCostBasis = false,
  int unmatchedOrdersCount = 0,
  List<String> notes = const [],
}) {
  return {
    'is_estimated': true,
    'has_complete_fills': hasCompleteFills,
    'missing_cost_basis': missingCostBasis,
    'unmatched_orders_count': unmatchedOrdersCount,
    'notes': notes,
  };
}

Map<String, dynamic> strategyDailyPerformanceJson() {
  return {
    'date': '2026-06-24',
    'provider': 'kis',
    'market': 'KR',
    'active_profile': strategyProfileJson(),
    'realized_pnl': 12000,
    'unrealized_pnl': -2000,
    'gross_pnl': 10000,
    'estimated_fees': 500,
    'net_pnl_estimated': 9500,
    'pnl_pct': 0.019,
    'orders_count': 4,
    'filled_orders_count': 3,
    'rejected_orders_count': 1,
    'winning_trades_count': 1,
    'losing_trades_count': 0,
    'win_rate': 1.0,
    'data_quality': strategyDataQualityJson(),
    'safety': strategySafetyJson(),
  };
}

Map<String, dynamic> strategyMonthlyPerformanceJson() {
  return {
    'month': '2026-06',
    'provider': 'kis',
    'market': 'KR',
    'active_profile': strategyProfileJson(),
    'monthly_target_return_pct': 0.04,
    'monthly_target_min_pct': 0.03,
    'monthly_target_max_pct': 0.05,
    'current_month_return_pct': 0.02,
    'target_progress_pct': 66.7,
    'monthly_max_loss_pct': -0.04,
    'loss_budget_used_pct': 0.0,
    'target_hit': false,
    'loss_limit_hit': false,
    'realized_pnl': 18000,
    'unrealized_pnl': 2000,
    'gross_pnl': 20000,
    'net_pnl_estimated': 19500,
    'estimated_fees': 500,
    'orders_count': 8,
    'filled_orders_count': 7,
    'rejected_orders_count': 1,
    'winning_trades_count': 3,
    'losing_trades_count': 1,
    'win_rate': 0.75,
    'average_win': 7000,
    'average_loss': -3000,
    'profit_factor': 7.0,
    'max_drawdown_pct': -0.006,
    'new_entries_allowed_by_target': true,
    'new_entries_block_reason': null,
    'data_quality': strategyDataQualityJson(),
    'safety': strategySafetyJson(),
  };
}

Map<String, dynamic> strategyTradePerformanceJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'count': 1,
    'items': [
      {
        'order_id': 12,
        'entry_order_id': 10,
        'exit_order_id': 12,
        'symbol': '005930',
        'symbol_name': 'Samsung Electronics',
        'provider': 'kis',
        'market': 'KR',
        'side': 'sell',
        'quantity': 2,
        'entry_price': 70000,
        'exit_price': 72000,
        'realized_pnl': 4000,
        'net_pnl_estimated': 3700,
        'pnl_pct': 0.02857,
        'holding_minutes': 120,
        'decision_source': 'manual',
        'risk_flags': const [],
        'gating_notes': const ['fifo_matched'],
        'created_at': '2026-06-24T01:00:00Z',
        'closed_at': '2026-06-24T03:00:00Z',
        'status': 'closed',
        'data_quality': strategyDataQualityJson(),
      },
    ],
    'data_quality': strategyDataQualityJson(),
    'safety': strategySafetyJson(),
  };
}

Map<String, dynamic> strategySafetyJson() {
  return {
    'read_only': true,
    'mutation': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'validation_called': false,
    'setting_changed': false,
    'scheduler_changed': false,
    'confirm_live_auto_checked': false,
  };
}
