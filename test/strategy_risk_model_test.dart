import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/strategy_risk.dart';

void main() {
  test('StrategyRiskState parses allowed state', () {
    final risk = StrategyRiskState.fromJson(
      strategyRiskJson(newEntriesAllowed: true),
    );

    expect(risk.activeProfile, 'balanced');
    expect(risk.newEntriesAllowed, isTrue);
    expect(risk.targetProgressPct, 30);
    expect(risk.recommendedOrderNotionalKrw, 40000);
    expect(risk.sizeReduced, isFalse);
  });

  test('StrategyRiskState parses blocked and reduced state', () {
    final risk = StrategyRiskState.fromJson(
      strategyRiskJson(
        newEntriesAllowed: false,
        primaryBlockReason: 'daily_loss_limit_hit',
        flags: const [
          'daily_loss_limit_hit',
          'consecutive_loss_size_reduced',
        ],
      ),
    );

    expect(risk.newEntriesAllowed, isFalse);
    expect(risk.primaryBlockReason, 'daily_loss_limit_hit');
    expect(risk.lossLimitHit, isTrue);
    expect(risk.sizeReduced, isTrue);
  });
}

Map<String, dynamic> strategyRiskJson({
  bool newEntriesAllowed = true,
  String? primaryBlockReason,
  List<String> flags = const [],
}) {
  return {
    'provider': 'kis',
    'market': 'KR',
    'active_profile': 'balanced',
    'monthly_target_return_pct': 0.04,
    'monthly_target_min_pct': 0.03,
    'monthly_target_max_pct': 0.05,
    'current_month_return_pct': 0.012,
    'target_progress_pct': 30.0,
    'target_hit': false,
    'monthly_max_loss_pct': -0.04,
    'loss_budget_used_pct': 0.0,
    'monthly_loss_limit_hit': false,
    'daily_max_loss_pct': -0.01,
    'current_daily_return_pct': -0.003,
    'daily_loss_limit_hit': !newEntriesAllowed,
    'max_order_notional_pct': 0.04,
    'max_order_notional_krw': 50000,
    'recommended_order_notional_pct': 0.04,
    'recommended_order_notional_krw': 40000,
    'max_trades_per_day': 2,
    'trades_used_today': 1,
    'trades_remaining_today': 1,
    'max_positions': 3,
    'current_positions_count': 1,
    'new_entries_allowed': newEntriesAllowed,
    'primary_block_reason': primaryBlockReason,
    'risk_flags': flags,
    'gating_notes': [
      if (primaryBlockReason != null) 'Risk gate blocked this entry.',
    ],
    'data_quality': {'mode': 'best_effort', 'limited': false, 'notes': []},
    'safety': {
      'read_only': true,
      'real_order_submitted': false,
      'validation_called': false,
      'setting_changed': false,
    },
  };
}
