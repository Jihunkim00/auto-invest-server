import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('US watchlist symbol parses company_name for display', () {
    final watchlist = MarketWatchlist.fromJson({
      'market': 'US',
      'currency': 'USD',
      'timezone': 'America/New_York',
      'watchlist_file': 'config/watchlist_us.yaml',
      'symbols': [
        {
          'symbol': 'NVDA',
          'company_name': 'NVIDIA Corporation',
          'market': 'US',
          'broker': 'alpaca',
          'market_label': '미국',
        },
      ],
    });

    expect(watchlist.symbols.single.symbol, 'NVDA');
    expect(watchlist.symbols.single.companyName, 'NVIDIA Corporation');
    expect(watchlist.symbols.single.name, 'NVIDIA Corporation');
    expect(watchlist.symbols.single.marketLabel, '미국');
  });

  test('Watchlist symbol falls back through name and company aliases', () {
    final watchlist = MarketWatchlist.fromJson({
      'market': 'US',
      'symbols': [
        {'symbol': 'AAPL', 'name': 'Apple Inc.'},
        {'symbol': 'MSFT', 'company': 'Microsoft Corporation'},
        {'ticker': 'GOOGL', 'companyName': 'Alphabet Inc.'},
      ],
    });

    expect(watchlist.symbols[0].companyName, 'Apple Inc.');
    expect(watchlist.symbols[1].companyName, 'Microsoft Corporation');
    expect(watchlist.symbols[2].symbol, 'GOOGL');
    expect(watchlist.symbols[2].companyName, 'Alphabet Inc.');
  });

  test('Watchlist symbol falls back to symbol instead of Unknown Company', () {
    final watchlist = MarketWatchlist.fromJson({
      'market': 'US',
      'symbols': [
        {'symbol': 'TSLA'},
      ],
    });

    expect(watchlist.symbols.single.companyName, 'TSLA');
    expect(watchlist.symbols.single.name, 'TSLA');
  });

  test('Watchlist symbol ignores Unknown Company when symbol exists', () {
    final watchlist = MarketWatchlist.fromJson({
      'market': 'US',
      'symbols': [
        {'symbol': 'AAPL', 'company_name': 'Unknown Company'},
      ],
    });

    expect(watchlist.symbols.single.companyName, 'AAPL');
    expect(watchlist.symbols.single.name, 'AAPL');
  });

  test('KIS watchlist parsing still preserves market metadata', () {
    final watchlist = MarketWatchlist.fromJson({
      'market': 'KR',
      'currency': 'KRW',
      'symbols': [
        {
          'symbol': '005930',
          'name': 'Samsung Electronics',
          'market': 'KOSPI',
          'market_label': '코스피',
        },
      ],
    });

    expect(watchlist.symbols.single.symbol, '005930');
    expect(watchlist.symbols.single.name, 'Samsung Electronics');
    expect(watchlist.symbols.single.companyName, 'Samsung Electronics');
    expect(watchlist.symbols.single.market, 'KOSPI');
    expect(watchlist.symbols.single.marketLabel, '코스피');
  });
}
