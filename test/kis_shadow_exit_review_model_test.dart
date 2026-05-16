import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_shadow_exit_review.dart';

void main() {
  test('parses KIS shadow exit review summary and decisions', () {
    final review = KisShadowExitReview.fromJson(_reviewJson());

    expect(review.status, 'ok');
    expect(review.mode, 'shadow_exit_review');
    expect(review.reviewWindowDays, 30);
    expect(review.summary.totalShadowRuns, 3);
    expect(review.summary.wouldSellCount, 1);
    expect(review.summary.holdCount, 1);
    expect(review.summary.manualReviewCount, 1);
    expect(review.summary.stopLossCount, 1);
    expect(review.summary.takeProfitCount, 0);
    expect(review.summary.insufficientCostBasisCount, 1);
    expect(review.summary.wouldSellRate, 1 / 3);
    expect(review.summary.manualSellFollowedCount, 1);
    expect(review.summary.manualSellFollowedRate, 1.0);
    expect(review.summary.noSubmitInvariantOk, isTrue);

    final decision = review.recentDecisions.first;
    expect(decision.runId, 10);
    expect(decision.runKey, 'shadow-linked');
    expect(decision.signalId, 3);
    expect(decision.symbol, '005930');
    expect(decision.decision, 'would_sell');
    expect(decision.action, 'sell');
    expect(decision.trigger, 'stop_loss');
    expect(decision.triggerSource, 'cost_basis_pl_pct');
    expect(decision.unrealizedPl, -2880);
    expect(decision.unrealizedPlPct, -0.02);
    expect(decision.costBasis, 144000);
    expect(decision.currentValue, 141120);
    expect(decision.suggestedQuantity, 2);
    expect(decision.riskFlags, contains('stop_loss_triggered'));
    expect(decision.gatingNotes, contains('no_broker_submit'));
    expect(decision.realOrderSubmitted, isFalse);
    expect(decision.brokerSubmitCalled, isFalse);
    expect(decision.manualSubmitCalled, isFalse);
    expect(decision.linkedManualOrderId, 44);
    expect(decision.linkedManualOrderStatus, 'FILLED');
  });

  test('parsing is null-safe and tolerant of missing fields', () {
    final review = KisShadowExitReview.fromJson({
      'summary': {
        'total_shadow_runs': '1',
        'no_submit_invariant_ok': false,
      },
      'recent_decisions': [
        {
          'symbol': '005930',
          'decision': 'hold',
          'unrealized_pl_pct': null,
        }
      ],
    });

    expect(review.status, 'ok');
    expect(review.mode, 'shadow_exit_review');
    expect(review.summary.totalShadowRuns, 1);
    expect(review.summary.noSubmitInvariantOk, isFalse);
    expect(review.safety.readOnly, isTrue);
    expect(review.safety.realOrderSubmitted, isFalse);
    expect(review.recentDecisions.single.unrealizedPlPct, isNull);
    expect(review.recentDecisions.single.linkedManualOrderStatus, isNull);
  });
}

Map<String, dynamic> _reviewJson() {
  return {
    'status': 'ok',
    'mode': 'shadow_exit_review',
    'review_window_days': 30,
    'summary': {
      'total_shadow_runs': 3,
      'would_sell_count': 1,
      'hold_count': 1,
      'manual_review_count': 1,
      'no_candidate_count': 1,
      'stop_loss_count': 1,
      'take_profit_count': 0,
      'manual_review_trigger_count': 1,
      'insufficient_cost_basis_count': 1,
      'unique_symbols_evaluated': 3,
      'manual_sell_followed_count': 1,
      'manual_sell_followed_rate': 1.0,
      'unmatched_shadow_would_sell_count': 0,
      'would_sell_rate': 1 / 3,
      'manual_review_rate': 1 / 3,
      'no_submit_invariant_ok': true,
    },
    'recent_decisions': [
      {
        'created_at': '2026-05-15T01:00:00+00:00',
        'run_id': 10,
        'run_key': 'shadow-linked',
        'signal_id': 3,
        'symbol': '005930',
        'decision': 'would_sell',
        'action': 'sell',
        'trigger': 'stop_loss',
        'trigger_source': 'cost_basis_pl_pct',
        'unrealized_pl': -2880,
        'unrealized_pl_pct': -0.02,
        'cost_basis': 144000,
        'current_value': 141120,
        'suggested_quantity': 2,
        'reason': 'Shadow decision only.',
        'risk_flags': ['stop_loss_triggered'],
        'gating_notes': ['no_broker_submit'],
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'linked_manual_order_id': 44,
        'linked_manual_order_status': 'FILLED',
      }
    ],
    'safety': {
      'read_only': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
      'no_submit_invariant_ok': true,
    },
    'created_at': '2026-05-15T01:05:00+00:00',
  };
}
