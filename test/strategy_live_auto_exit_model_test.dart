import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/strategy_live_auto_exit.dart';

void main() {
  test('readiness model parses ready response with candidates', () {
    final readiness = StrategyLiveAutoExitReadiness.fromJson(
      liveExitReadinessJson(ready: true),
    );

    expect(readiness.ready, isTrue);
    expect(readiness.enabled, isTrue);
    expect(readiness.activeProfile, 'safe');
    expect(readiness.selectedSymbol, '005930');
    expect(readiness.selectedTrigger, 'stop_loss');
    expect(readiness.ordersRemainingToday, 1);
    expect(readiness.candidates.single.trigger, 'stop_loss');
    expect(readiness.safety['read_only'], isTrue);
  });

  test('run result parses submitted and blocked states', () {
    final submitted = StrategyLiveAutoExitRunResult.fromJson(
      liveExitRunResultJson(status: 'submitted', submitted: true),
    );
    final blocked = StrategyLiveAutoExitRunResult.fromJson(
      liveExitRunResultJson(
        status: 'blocked',
        action: 'blocked',
        blockReason: 'cost_basis_unavailable',
      ),
    );

    expect(submitted.submitted, isTrue);
    expect(submitted.brokerOrderId, 'KIS-SELL-1');
    expect(submitted.exitTrigger, 'stop_loss');
    expect(blocked.blocked, isTrue);
    expect(blocked.blockReason, 'cost_basis_unavailable');
  });
}

Map<String, dynamic> liveExitReadinessJson({bool ready = false}) {
  return {
    'enabled': true,
    'ready': ready,
    'provider': 'kis',
    'market': 'KR',
    'active_profile': 'safe',
    'allowed_profiles': ['safe', 'balanced'],
    'dry_run': false,
    'kill_switch': false,
    'kis_enabled': true,
    'kis_real_order_enabled': true,
    'scheduler_live_enabled': false,
    'positions_count': 1,
    'candidate_count': 1,
    'selected_symbol': '005930',
    'selected_trigger': 'stop_loss',
    'max_orders_per_day': 1,
    'orders_used_today': 0,
    'orders_remaining_today': 1,
    'primary_block_reason': ready ? null : 'strategy_live_auto_exit_disabled',
    'checks': [
      {'key': 'eligible_exit_candidate', 'ok': true}
    ],
    'candidates': [
      {
        'symbol': '005930',
        'symbol_name': 'Samsung Electronics',
        'quantity': 3,
        'current_price': 9000,
        'cost_basis': 30000,
        'current_value': 27000,
        'unrealized_pnl': -3000,
        'unrealized_pnl_pct': -0.1,
        'stop_loss_pct': -0.012,
        'take_profit_pct': 0.02,
        'position_age_days': 2,
        'max_holding_days': 5,
        'trigger': 'stop_loss',
        'reason': 'stop_loss_threshold_reached',
        'eligible': true,
        'risk_flags': ['stop_loss_triggered'],
        'gating_notes': ['Held position exit candidate passed.'],
        'data_quality': {'cost_basis_valid': true},
      }
    ],
    'risk_flags': ready ? [] : ['strategy_live_auto_exit_disabled'],
    'gating_notes': ['Stop-loss candidate found.'],
    'safety': {
      'read_only': true,
      'validation_called': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
  };
}

Map<String, dynamic> liveExitRunResultJson({
  String status = 'submitted',
  String action = 'submitted',
  bool submitted = false,
  String? blockReason,
}) {
  return {
    'status': status,
    'action': action,
    'provider': 'kis',
    'market': 'KR',
    'active_profile': 'safe',
    'symbol': '005930',
    'symbol_name': 'Samsung Electronics',
    'exit_trigger': 'stop_loss',
    'exit_reason': 'stop_loss_threshold_reached',
    'submitted': submitted,
    'quantity': submitted ? 3 : 0,
    'current_price': 9000,
    'submitted_notional_krw': submitted ? 27000 : 0,
    'related_order_id': submitted ? 30 : null,
    'broker_order_id': submitted ? 'KIS-SELL-1' : null,
    'broker_status': submitted ? 'accepted' : null,
    'internal_status': submitted ? 'SUBMITTED' : null,
    'block_reason': blockReason,
    'risk_flags': blockReason == null ? [] : [blockReason],
    'gating_notes': ['All guarded live auto exit gates passed.'],
    'attempt_id': 10,
    'signal_id': submitted ? 11 : null,
    'trade_run_id': submitted ? 12 : null,
    'created_at': '2026-06-25T03:00:00Z',
    'safety': {
      'real_order_submitted': submitted,
      'validation_called': submitted,
      'broker_submit_called': submitted,
      'manual_submit_called': false,
      'scheduler_changed': false,
    },
  };
}
