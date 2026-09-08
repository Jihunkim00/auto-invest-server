import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/utils/kr_stock_catalog.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('loads the lookup-only asset once and resolves required aliases',
      () async {
    var loadCalls = 0;
    final catalog = KrStockCatalog(
      loadString: (path) async {
        loadCalls += 1;
        return rootBundle.loadString(path);
      },
    );

    await catalog.load();
    await catalog.load();

    expect(loadCalls, 1);
    expect(catalog.entries, hasLength(200));
    expect(
      catalog.entries.where((entry) => entry.market == 'KOSPI'),
      hasLength(150),
    );
    expect(
      catalog.entries.where((entry) => entry.market == 'KOSDAQ'),
      hasLength(50),
    );

    for (final query in [
      'SK하이닉스',
      'SK 하이닉스',
      'SK하이닉스 가격입니다',
      'hynix',
      'SKHynix',
      'SK hynix',
      '하이닉스 가격입니다',
    ]) {
      expect(catalog.resolve(query)?.symbol, '000660', reason: query);
    }
    expect(catalog.resolve('삼성전자')?.symbol, '005930');
    expect(catalog.resolve('삼성전')?.symbol, '005930');
    expect(catalog.resolve('현대자동차')?.symbol, '005380');
    expect(catalog.resolve('현대건설')?.symbol, '000720');
    expect(catalog.resolve('000660')?.symbol, '000660');
    expect(catalog.displayName('000660'), 'SK하이닉스');
  });

  test('does not read or mutate the active automation watchlist', () async {
    final active = MarketWatchlist.empty('KR');
    final catalog = KrStockCatalog(
      loadString: (path) async => rootBundle.loadString(path),
    );

    await catalog.load();

    expect(active.symbols, isEmpty);
    expect(catalog.resolve('SK하이닉스 가격입니다')?.symbol, '000660');
    expect(active.symbols, isEmpty);
  });

  test('rejects ambiguous partial aliases', () async {
    final catalog = KrStockCatalog(
      loadString: (_) async => jsonEncode({
        'symbols': [
          {
            'symbol': '000001',
            'name': '알파',
            'english_name': 'Alpha',
            'market': 'KOSPI',
            'aliases': ['공통'],
          },
          {
            'symbol': '000002',
            'name': '베타',
            'english_name': 'Beta',
            'market': 'KOSPI',
            'aliases': ['공통'],
          },
        ],
      }),
    );

    await catalog.load();

    expect(catalog.resolve('공통 가격'), isNull);
    expect(catalog.resolve('Alpha 가격')?.symbol, '000001');
  });
}
