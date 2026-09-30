import 'package:flutter_test/flutter_test.dart';
import 'package:auto_invest_dashboard/models/market_regime.dart';

void main() {
  test('parses regime scores, diagnostics, source, and transition conditions',
      () {
    final model = MarketRegime.fromJson({
      'status': 'confirmed',
      'stage': 4,
      'stage_key': 'rising',
      'stage_label': '상승 진행',
      'short_label': '상승',
      'market_score': 61.23,
      'score_change_3w': 5.73,
      'kospi_score': 56.70,
      'nasdaq_score': 67.37,
      'confirmed': true,
      'kospi': {'close': 2800, 'ema20': 2700, 'drawdown_52w': 4.25},
      'nasdaq': {'close': 18000, 'rsi14': 61},
      'data_source': {
        'kospi': {'provider': 'Yahoo Finance chart', 'symbol': '^KS11'},
        'nasdaq': {
          'provider': 'Yahoo Finance chart',
          'symbol': '^IXIC',
          'label': 'NASDAQ Composite',
          'is_proxy': false,
        },
        'nasdaq_is_proxy': false,
      },
      'bullish_transition': {
        'passed': 2,
        'total': 8,
        'conditions': [
          {'key': 'combined_score', 'label': '시장 점수 >= 60', 'passed': true},
        ],
      },
    });

    expect(model.stage, 4);
    expect(model.marketScore, 61.23);
    expect(model.kospi.close, 2800);
    expect(model.kospi.drawdown52w, 4.25);
    expect(model.nasdaq.rsi14, 61);
    expect(model.dataSource.nasdaqIsProxy, isFalse);
    expect(model.bullishTransition.conditions.single.passed, isTrue);
  });

  test('handles nullable or missing API values safely', () {
    final model = MarketRegime.fromJson({
      'status': 'insufficient_data',
      'stage': null,
      'market_score': 'NaN',
      'kospi': null,
      'nasdaq': {},
      'bullish_transition': {'conditions': 'invalid'},
      'data_source': null,
    });

    expect(model.status, 'insufficient_data');
    expect(model.stage, isNull);
    expect(model.marketScore, isNull);
    expect(model.kospi.close, isNull);
    expect(model.bullishTransition.conditions, isEmpty);
    expect(model.dataSource.nasdaqIsProxy, isFalse);
  });

  test('rejects invalid stage values and unknown status', () {
    final model = MarketRegime.fromJson({'status': 'unexpected', 'stage': 9});
    expect(model.status, 'insufficient_data');
    expect(model.stage, isNull);
  });
}
