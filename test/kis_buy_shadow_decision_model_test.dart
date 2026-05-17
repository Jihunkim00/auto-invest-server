import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_buy_shadow_decision.dart';

void main() {
  test('model parses hold response', () {
    final result = KisBuyShadowDecision.fromJson({
      'status': 'ok',
      'mode': 'shadow_buy_dry_run',
      'decision': 'hold',
      'action': 'hold',
      'reason': 'score_threshold_not_met',
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
      'checks': {'score_threshold_ok': false},
      'safety': {'read_only': true},
      'failed_checks': ['score_threshold'],
    });

    expect(result.mode, 'shadow_buy_dry_run');
    expect(result.decision, 'hold');
    expect(result.action, 'hold');
    expect(result.realOrderSubmitted, isFalse);
    expect(result.brokerSubmitCalled, isFalse);
    expect(result.manualSubmitCalled, isFalse);
    expect(result.candidate, isNull);
    expect(result.failedChecks, contains('score_threshold'));
  });

  test('model parses would_buy candidate response', () {
    final result = KisBuyShadowDecision.fromJson({
      'status': 'ok',
      'mode': 'shadow_buy_dry_run',
      'decision': 'would_buy',
      'action': 'buy',
      'reason': 'Shadow buy candidate only. No broker submit.',
      'symbol': '005930',
      'candidate': {
        'symbol': '005930',
        'market': 'KR',
        'provider': 'kis',
        'final_score': 82.5,
        'confidence': 0.76,
        'quant_score': 78,
        'gpt_buy_score': 65,
        'current_price': 72000,
        'suggested_notional': 288000,
        'suggested_quantity': 4,
        'reason': 'candidate',
        'risk_flags': ['shadow_buy_only'],
        'gating_notes': ['no_broker_submit'],
        'audit_metadata': {'source': 'kis_buy_shadow_decision'},
        'gpt_context': {'hard_block_new_buy': false},
      },
      'checks': {'notional_cap_ok': true},
      'safety': {
        'read_only': true,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      },
    });

    expect(result.isWouldBuy, isTrue);
    expect(result.candidate?.symbol, '005930');
    expect(result.candidate?.finalScore, 82.5);
    expect(result.candidate?.confidence, 0.76);
    expect(result.candidate?.suggestedNotional, 288000);
    expect(result.candidate?.suggestedQuantity, 4);
    expect(
        result.candidate?.auditMetadata['source'], 'kis_buy_shadow_decision');
  });
}
