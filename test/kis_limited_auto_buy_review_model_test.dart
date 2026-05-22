import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/kis_limited_auto_buy_review.dart';

void main() {
  test('parses limited buy review summary and recent decisions', () {
    final review = KisLimitedAutoBuyReview.fromJson(_reviewPayload());

    expect(review.mode, 'kis_limited_auto_buy_review');
    expect(review.reviewOnly, isTrue);
    expect(review.realOrderSubmitted, isFalse);
    expect(review.brokerSubmitCalled, isFalse);
    expect(review.summary.totalRuns, 2);
    expect(review.summary.buyReadyCount, 1);
    expect(review.summary.blockedCount, 1);
    expect(review.summary.avgFinalBuyScore, 71.25);
    expect(review.summary.noSubmitInvariantOk, isTrue);
    expect(review.topBlockReasons.single.label, 'Score threshold not met');
    expect(review.recentDecisions.first.status, 'BUY_READY');
    expect(review.recentDecisions.first.symbol, '005930');
    expect(review.recentDecisions.first.companyName, 'Samsung Electronics');
    expect(review.recentDecisions.first.brokerSubmitCalled, isFalse);
  });
}

Map<String, dynamic> _reviewPayload() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_limited_auto_buy_review',
    'review_only': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'summary': {
      'total_runs': 2,
      'buy_ready_count': 1,
      'blocked_count': 1,
      'no_candidate_count': 0,
      'insufficient_cash_count': 0,
      'score_threshold_not_met_count': 1,
      'sell_pressure_too_high_count': 0,
      'duplicate_position_count': 0,
      'duplicate_open_order_count': 0,
      'daily_limit_reached_count': 0,
      'market_session_block_count': 0,
      'no_new_entry_after_block_count': 0,
      'missing_indicators_count': 0,
      'avg_final_buy_score': 71.25,
      'avg_final_sell_score': 12,
      'avg_required_buy_score': 75,
      'avg_confidence': 0.76,
      'latest_run_at': '2026-05-22T01:00:00+00:00',
      'latest_candidate_symbol': '005930',
      'latest_candidate_company': 'Samsung Electronics',
      'no_submit_invariant_ok': true,
    },
    'recent_decisions': [_decision()],
    'top_block_reasons': [
      {
        'reason': 'score_threshold_not_met',
        'count': 1,
        'label': 'Score threshold not met',
      }
    ],
    'latest_buy_ready': _decision(),
    'safety': {'review_only': true},
    'diagnostics': {'rows_scanned': 2},
  };
}

Map<String, dynamic> _decision() {
  return {
    'run_id': 7,
    'signal_id': 5,
    'created_at': '2026-05-22T01:00:00+00:00',
    'trigger_source': 'limited_auto_buy_run_once',
    'symbol': '005930',
    'company_name': 'Samsung Electronics',
    'result': 'readiness_only',
    'action': 'buy_ready',
    'status': 'BUY_READY',
    'final_buy_score': 82.5,
    'required_buy_score': 75,
    'final_sell_score': 12,
    'confidence': 0.76,
    'buy_sell_spread': 70.5,
    'estimated_notional': 288000,
    'suggested_quantity': 4,
    'cash_available': 3000000,
    'block_reasons': ['auto_buy_execution_disabled'],
    'primary_block_reason': 'auto_buy_execution_disabled',
    'reason': 'buy_readiness_only',
    'gate_level': 2,
    'duplicate_position': false,
    'duplicate_open_order': false,
    'market_session_allowed': true,
    'no_new_entry_after_blocked': false,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
  };
}
