import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/strategy_live_auto_buy.dart';

void main() {
  test('readiness model parses ready response', () {
    final readiness = StrategyLiveAutoBuyReadiness.fromJson(
      liveReadinessJson(ready: true),
    );

    expect(readiness.ready, isTrue);
    expect(readiness.enabled, isTrue);
    expect(readiness.activeProfile, 'safe');
    expect(readiness.selectedSymbol, '005930');
    expect(readiness.ordersRemainingToday, 1);
    expect(readiness.safety['read_only'], isTrue);
  });

  test('run result parses submitted and blocked states', () {
    final submitted = StrategyLiveAutoBuyRunResult.fromJson(
      liveRunResultJson(status: 'submitted', submitted: true),
    );
    final blocked = StrategyLiveAutoBuyRunResult.fromJson(
      liveRunResultJson(
        status: 'blocked',
        action: 'blocked',
        blockReason: 'recent_dry_run_missing',
      ),
    );

    expect(submitted.submitted, isTrue);
    expect(submitted.brokerOrderId, 'KIS-ORDER-1');
    expect(submitted.sourceSignalId, 123);
    expect(submitted.sourceTradeRunId, 20);
    expect(blocked.blocked, isTrue);
    expect(blocked.blockReason, 'recent_dry_run_missing');
  });
}

Map<String, dynamic> liveReadinessJson({bool ready = false}) {
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
    'recent_dry_run_required': true,
    'recent_dry_run_found': true,
    'recent_dry_run_age_minutes': 4.5,
    'recent_dry_run_ttl_minutes': 30,
    'selected_symbol': '005930',
    'max_orders_per_day': 1,
    'orders_used_today': 0,
    'orders_remaining_today': 1,
    'max_notional_krw': 50000,
    'max_notional_pct': 0.03,
    'primary_block_reason': ready ? null : 'strategy_live_auto_buy_disabled',
    'checks': [
      {'key': 'recent_dry_run_would_buy', 'ok': true}
    ],
    'risk_flags': ready ? [] : ['strategy_live_auto_buy_disabled'],
    'gating_notes': ['Target-aware risk will rerun before submit.'],
    'safety': {
      'read_only': true,
      'validation_called': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
  };
}

Map<String, dynamic> liveRunResultJson({
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
    'source_dry_run_id': 20,
    'source_signal_id': 123,
    'source_trade_run_id': 20,
    'target_risk_approved': true,
    'validation_approved': submitted,
    'submitted': submitted,
    'quantity': submitted ? 3 : 0,
    'estimated_price': 10000,
    'submitted_notional_krw': submitted ? 30000 : 0,
    'related_order_id': submitted ? 30 : null,
    'broker_order_id': submitted ? 'KIS-ORDER-1' : null,
    'broker_status': submitted ? 'accepted' : null,
    'internal_status': submitted ? 'SUBMITTED' : null,
    'block_reason': blockReason,
    'risk_flags': blockReason == null ? [] : [blockReason],
    'gating_notes': ['All guarded gates passed.'],
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
