import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/utils/kr_symbol.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';

void main() {
  final watchlist = MarketWatchlist.fromJson({
    'market': 'KR',
    'symbols': [
      {'symbol': '005930', 'name': '삼성전자'},
      {'symbol': '000660', 'name': 'SK하이닉스'},
      {'symbol': '035420', 'name': 'NAVER'},
    ],
  });

  test('resolves Korean names from the watchlist for quote requests', () {
    expect(resolveKrStockText('삼성전자 현재가', watchlist)?.symbol, '005930');
    expect(resolveKrStockText('SK하이닉스 현재가', watchlist)?.symbol, '000660');
    expect(resolveKrStockText('NAVER 분석', watchlist)?.symbol, '035420');
  });

  test('formats known and unknown KR stocks as name plus code', () {
    expect(
      formatKrStockDisplay('000660', watchlist: watchlist),
      'SK하이닉스 (000660)',
    );
    expect(
      formatKrStockDisplay('267250'),
      '종목명 미확인 (267250)',
    );
  });

  test('supports aliases and raw six-digit symbols without hardcoded names',
      () {
    final aliasWatchlist = MarketWatchlist.fromJson({
      'market': 'KR',
      'symbols': [
        {
          'symbol': '000660',
          'name': 'SK\uD558\uC774\uB2C9\uC2A4',
          'aliases': ['\uD558\uC774\uB2C9\uC2A4'],
        },
        {'symbol': '000720', 'name': '\uD604\uB300\uAC74\uC124'},
        {'symbol': '267250', 'name': 'HD\uD604\uB300\uC77C\uB809\uD2B8\uB9AD'},
      ],
    });

    expect(
      resolveKrStockText(
              '\uD558\uC774\uB2C9\uC2A4 \uAC00\uACA9', aliasWatchlist)
          ?.symbol,
      '000660',
    );
    expect(
      resolveKrStockText(
              'SK\uD558\uC774\uB2C9\uC2A4 \uAC00\uACA9', aliasWatchlist)
          ?.symbol,
      '000660',
    );
    expect(
      resolveKrStockText(
              'SK-\uD558\uC774\uB2C9\uC2A4 (000660) \uD604\uC7AC\uAC00',
              aliasWatchlist)
          ?.symbol,
      '000660',
    );
    expect(
      resolveKrStockText(
              '\uD604\uB300\uAC74\uC124 \uD604\uC7AC\uAC00', aliasWatchlist)
          ?.symbol,
      '000720',
    );
    expect(
      resolveKrStockText(
              '000720 \uD604\uC7AC\uAC00', MarketWatchlist.empty('KR'))
          ?.symbol,
      '000720',
    );
    expect(
      formatKrStockDisplay(
        '267250',
        watchlist: aliasWatchlist,
      ),
      contains('(267250)'),
    );
  });
}
