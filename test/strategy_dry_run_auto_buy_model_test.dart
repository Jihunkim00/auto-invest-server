import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/strategy_dry_run_auto_buy.dart';

void main() {
  test('model parses would_buy result', () {
    final result = StrategyDryRunAutoBuyResult.fromJson(
      dryRunResultJson(action: 'would_buy'),
    );

    expect(result.wouldBuy, isTrue);
    expect(result.activeProfile, 'balanced');
    expect(result.selectedSymbol, '005930');
    expect(result.simulatedQuantity, 3);
    expect(result.targetRiskApproved, isTrue);
    expect(result.signalId, 10);
  });

  test('model parses blocked result', () {
    final result = StrategyDryRunAutoBuyResult.fromJson(
      dryRunResultJson(
        action: 'blocked',
        reason: 'below_profile_buy_threshold',
      ),
    );

    expect(result.blocked, isTrue);
    expect(result.reason, 'below_profile_buy_threshold');
    expect(result.simulatedQuantity, 0);
  });
}

Map<String, dynamic> dryRunResultJson({
  String action = 'would_buy',
  String reason = 'target_aware_risk_approved',
}) {
  final wouldBuy = action == 'would_buy';
  return {
    'status': 'ok',
    'action': action,
    'provider': 'kis',
    'market': 'KR',
    'active_profile': 'balanced',
    'selected_symbol': '005930',
    'selected_symbol_name': 'Samsung Electronics',
    'candidate_count': 1,
    'candidates': [
      {
        'symbol': '005930',
        'buy_score': 72,
        'target_risk_approved': wouldBuy,
      }
    ],
    'buy_score': 72,
    'sell_score': 15,
    'final_score': 72,
    'confidence': 0.8,
    'target_risk_approved': wouldBuy,
    'target_risk_result': {'approved': wouldBuy},
    'recommended_notional_krw': wouldBuy ? 30000 : 0,
    'recommended_notional_pct': wouldBuy ? 0.03 : 0,
    'simulated_quantity': wouldBuy ? 3 : 0,
    'simulated_price': 10000,
    'simulated_notional_krw': wouldBuy ? 30000 : 0,
    'reason': reason,
    'risk_flags': [
      'dry_run_only',
      if (!wouldBuy) 'below_profile_buy_threshold',
    ],
    'gating_notes': ['No order submitted.'],
    'signal_id': 10,
    'trade_run_id': 20,
    'simulated_order_id': wouldBuy ? 30 : null,
    'data_quality': {'sufficient_for_would_buy': wouldBuy, 'notes': []},
    'safety': {
      'dry_run_only': true,
      'real_order_submitted': false,
      'validation_called': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
    'created_at': '2026-06-25T03:00:00Z',
  };
}
