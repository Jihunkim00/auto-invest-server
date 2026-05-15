import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_exit_shadow_decision.dart';

void main() {
  test('parses would-sell shadow decision and candidate safety fields', () {
    final result = KisExitShadowDecision.fromJson({
      'status': 'ok',
      'provider': 'kis',
      'market': 'KR',
      'mode': 'shadow_exit_dry_run',
      'source': 'kis_exit_shadow_decision',
      'source_type': 'dry_run_sell_simulation',
      'decision': 'would_sell',
      'action': 'sell',
      'reason': 'would_sell_stop_loss',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'real_order_submit_allowed': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
      'manual_confirm_required': true,
      'created_at': '2026-05-15T01:00:00+00:00',
      'candidate': {
        'symbol': '005930',
        'side': 'sell',
        'quantity_available': 2,
        'suggested_quantity': 1,
        'trigger': 'stop_loss',
        'trigger_source': 'cost_basis_pl_pct',
        'current_price': 70560,
        'cost_basis': 144000,
        'current_value': 141120,
        'unrealized_pl': -2880,
        'unrealized_pl_pct': -0.02,
        'reason': 'Shadow decision only.',
        'risk_flags': ['stop_loss_triggered'],
        'gating_notes': ['shadow_exit_only', 'no_broker_submit'],
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'real_order_submit_allowed': false,
        'manual_confirm_required': true,
        'audit_metadata': {
          'source': 'kis_exit_shadow_decision',
          'source_type': 'dry_run_sell_simulation',
          'exit_trigger': 'stop_loss',
          'trigger_source': 'cost_basis_pl_pct',
          'shadow_real_order_submitted': false,
        },
      },
      'checks': {'positions_available': true, 'cost_basis_available': true},
      'safety': {
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      },
    });

    expect(result.mode, 'shadow_exit_dry_run');
    expect(result.isWouldSell, isTrue);
    expect(result.realOrderSubmitted, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
    expect(result.manualSubmitCalled, isFalse);
    expect(result.realOrderSubmitAllowed, isFalse);
    expect(result.autoSellEnabled, isFalse);
    expect(result.schedulerRealOrderEnabled, isFalse);
    expect(result.manualConfirmRequired, isTrue);
    expect(result.check('positions_available'), isTrue);

    final candidate = result.candidate!;
    expect(candidate.symbol, '005930');
    expect(candidate.trigger, 'stop_loss');
    expect(candidate.triggerSource, 'cost_basis_pl_pct');
    expect(candidate.suggestedQuantityInt, 1);
    expect(candidate.hasSafePlPct, isTrue);
    expect(candidate.unrealizedPlPct, -0.02);
    expect(candidate.auditMetadata['source'], 'kis_exit_shadow_decision');
  });

  test('parses hold decision and missing P/L fields safely', () {
    final result = KisExitShadowDecision.fromJson({
      'decision': 'hold',
      'action': 'hold',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'candidates_evaluated': [
        {
          'symbol': '005930',
          'side': 'sell',
          'trigger': 'none',
          'trigger_source': 'cost_basis_pl_pct',
        }
      ],
    });

    expect(result.provider, 'kis');
    expect(result.market, 'KR');
    expect(result.mode, 'shadow_exit_dry_run');
    expect(result.isWouldSell, isFalse);
    expect(result.candidate, isNull);
    expect(result.candidatesEvaluated, hasLength(1));
    expect(result.candidatesEvaluated.single.costBasis, isNull);
    expect(result.candidatesEvaluated.single.hasSafePlPct, isFalse);
  });
}
