import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/auto_exit_candidate.dart';

void main() {
  test('auto exit candidate model parses PR92 response', () {
    final payload = AutoExitCandidates.fromJson(autoExitCandidatesJson());

    expect(payload.provider, 'kis');
    expect(payload.market, 'KR');
    expect(payload.summary.candidateCount, 2);
    expect(payload.summary.stopLossCount, 1);
    expect(payload.summary.syncRequiredCount, 1);
    expect(payload.safetyFlags, contains('read_only'));

    final stopLoss = payload.candidates.first;
    expect(stopLoss.candidateId, 'auto-exit:kis:KR:005930:stop_loss:20260707');
    expect(stopLoss.symbol, '005930');
    expect(stopLoss.candidateType, 'stop_loss');
    expect(stopLoss.severity, 'critical');
    expect(stopLoss.actionHint, 'run_sell_preflight');
    expect(stopLoss.costBasis, 10000);
    expect(stopLoss.currentValue, 9800);
    expect(stopLoss.unrealizedPlPct, -0.02);
    expect(stopLoss.canRunSellPreflight, isTrue);
    expect(stopLoss.sellPreflightEndpointHint,
        '/strategy/positions/005930/sell-preflight');

    final sync = payload.candidates.last;
    expect(sync.candidateType, 'sync_required');
    expect(sync.canRunSellPreflight, isFalse);
    expect(sync.syncRequired, isTrue);
  });
}

Map<String, dynamic> autoExitCandidatesJson() {
  return {
    'generated_at': '2026-07-07T09:00:00Z',
    'timezone': 'Asia/Seoul',
    'provider': 'kis',
    'market': 'KR',
    'summary': {
      'candidate_count': 2,
      'critical_count': 1,
      'warning_count': 1,
      'info_count': 0,
      'stop_loss_count': 1,
      'take_profit_count': 0,
      'trend_breakdown_count': 0,
      'manual_review_count': 0,
      'duplicate_sell_block_count': 0,
      'sync_required_count': 1,
    },
    'safety_flags': const [
      'read_only',
      'no_live_orders',
      'no_broker_submit',
    ],
    'candidates': [
      _candidate('stop_loss', severity: 'critical'),
      _candidate(
        'sync_required',
        severity: 'warning',
        canRunPreflight: false,
        syncRequired: true,
      ),
    ],
    'details': const {'position_count': 1},
  };
}

Map<String, dynamic> _candidate(
  String type, {
  String severity = 'warning',
  bool canRunPreflight = true,
  bool syncRequired = false,
}) {
  return {
    'candidate_id': 'auto-exit:kis:KR:005930:$type:20260707',
    'symbol': '005930',
    'provider': 'kis',
    'market': 'KR',
    'candidate_type': type,
    'severity': severity,
    'status': 'active',
    'action_hint': syncRequired ? 'sync_required' : 'run_sell_preflight',
    'position_quantity': 2,
    'available_quantity': 2,
    'average_price': 5000,
    'current_price': 4900,
    'cost_basis': 10000,
    'current_value': 9800,
    'unrealized_pl': -200,
    'unrealized_pl_pct': -0.02,
    'stop_loss_threshold_pct': 2,
    'take_profit_threshold_pct': 2,
    'stop_loss_triggered': type == 'stop_loss',
    'take_profit_triggered': false,
    'trend_breakdown_triggered': false,
    'momentum_note': null,
    'risk_flags': [type],
    'gating_notes': const ['Read-only candidate detection.'],
    'primary_reason': 'Stop-loss threshold was reached.',
    'next_safe_action': 'Run sell preflight for operator review.',
    'related_position_id': null,
    'related_buy_order_id': 7,
    'related_lifecycle_id': null,
    'open_sell_order_conflict': false,
    'sync_required': syncRequired,
    'can_run_sell_preflight': canRunPreflight,
    'sell_preflight_endpoint_hint':
        canRunPreflight ? '/strategy/positions/005930/sell-preflight' : null,
  };
}
