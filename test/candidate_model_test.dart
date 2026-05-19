import 'package:auto_invest_dashboard/models/candidate.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Candidate parses company name aliases and detailed readiness fields',
      () {
    final candidate = Candidate.fromJson({
      'symbol': '005930',
      'company_name': 'Samsung Electronics',
      'provider': 'kis',
      'market': 'KOSPI',
      'currency': 'KRW',
      'readiness': {
        'effective_min_entry_score': 56,
        'buy_sell_spread': 34,
      },
      'analysis': {
        'current_price': 72000,
        'indicator_status': 'ok',
        'indicator_bar_count': 100,
        'indicator_payload': {
          'ema20': 70000,
          'ema50': 68000,
          'vwap': 70500,
          'rsi': 58.5,
        },
      },
    });

    expect(candidate.name, 'Samsung Electronics');
    expect(candidate.provider, 'kis');
    expect(candidate.market, 'KOSPI');
    expect(candidate.currentPrice, 72000);
    expect(candidate.indicatorStatus, 'ok');
    expect(candidate.indicatorBarCount, 100);
    expect(candidate.effectiveMinEntryScore, 56);
    expect(candidate.buySellSpread, 34);
    expect(candidate.indicatorPayload['vwap'], 70500);
  });

  test('Candidate without company name remains safe to render with empty name',
      () {
    final candidate = Candidate.fromJson({
      'symbol': 'AAPL',
      'final_entry_score': 66,
      'block_reason': 'score_threshold_not_met',
    }, scoreKey: 'final_entry_score', noteKey: 'reason');

    expect(candidate.symbol, 'AAPL');
    expect(candidate.name, '');
    expect(candidate.finalEntryScore, 66);
    expect(candidate.blockReason, 'score_threshold_not_met');
  });
}
