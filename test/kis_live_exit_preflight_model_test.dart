import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_live_exit_preflight.dart';

void main() {
  test('parses manual-confirm exit candidates and safety flags', () {
    final result = KisLiveExitPreflightResult.fromJson({
      'status': 'ok',
      'provider': 'kis',
      'market': 'KR',
      'mode': 'kis_live_exit_preflight',
      'execution_mode': 'manual_confirm_only',
      'live_auto_enabled': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'real_order_submit_allowed': false,
      'manual_confirm_required': true,
      'candidate_count': 1,
      'action': 'sell',
      'symbol': '005930',
      'qty': 1,
      'reason': 'take_profit_triggered',
      'would_submit_if_enabled': true,
      'live_order_submitted': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'safety': {
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'scheduler_real_order_enabled': false,
        'auto_buy_enabled': false,
        'auto_sell_enabled': false,
        'manual_confirm_required': true,
      },
      'candidates': [
        {
          'symbol': '005930',
          'side': 'sell',
          'quantity_available': 1,
          'suggested_quantity': 1,
          'current_price': 72000,
          'cost_basis': 70000,
          'current_value': 72000,
          'unrealized_pl': 2000,
          'unrealized_pl_pct': 2000 / 70000,
          'trigger': 'take_profit',
          'trigger_source': 'cost_basis_pl_pct',
          'severity': 'review',
          'action_hint': 'manual_confirm_sell',
          'reason': 'Manual confirmation is required.',
          'risk_flags': ['take_profit_triggered'],
          'gating_notes': ['manual_confirm_required', 'no_auto_submit'],
          'submit_ready': false,
          'manual_confirm_required': true,
          'real_order_submit_allowed': false,
          'real_order_submitted': false,
          'broker_submit_called': false,
          'manual_submit_called': false,
        },
      ],
    });

    expect(result.status, 'ok');
    expect(result.executionMode, 'manual_confirm_only');
    expect(result.liveAutoEnabled, isFalse);
    expect(result.autoBuyEnabled, isFalse);
    expect(result.autoSellEnabled, isFalse);
    expect(result.realOrderSubmitAllowed, isFalse);
    expect(result.manualConfirmRequired, isTrue);
    expect(result.safetyFlag('scheduler_real_order_enabled'), isFalse);
    expect(result.safetyFlag('manual_confirm_required'), isTrue);
    expect(result.candidateCount, 1);
    expect(result.candidates, hasLength(1));

    final candidate = result.candidates.single;
    expect(candidate.symbol, '005930');
    expect(candidate.side, 'sell');
    expect(candidate.suggestedQuantityInt, 1);
    expect(candidate.trigger, 'take_profit');
    expect(candidate.triggerSource, 'cost_basis_pl_pct');
    expect(candidate.actionHint, 'manual_confirm_sell');
    expect(candidate.submitReady, isFalse);
    expect(candidate.realOrderSubmitAllowed, isFalse);
    expect(candidate.hasSafePlPct, isTrue);
  });

  test('is tolerant of missing fields and unsafe P/L inputs', () {
    final result = KisLiveExitPreflightResult.fromJson({
      'action': 'sell',
      'symbol': '005930',
      'qty': 2,
      'reason': 'risk_exit',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'would_submit_if_enabled': false,
      'candidates': [
        {
          'symbol': '005930',
          'side': 'sell',
          'suggested_quantity': 2,
          'unrealized_pl_pct': 0.02,
          'cost_basis': null,
        },
      ],
    });

    expect(result.provider, 'kis');
    expect(result.market, 'KR');
    expect(result.realOrderSubmitAllowed, isFalse);
    expect(result.manualConfirmRequired, isTrue);
    expect(result.candidateCount, 1);
    expect(result.candidates.single.hasSafePlPct, isFalse);
    expect(result.candidates.single.submitReady, isFalse);
  });
}
