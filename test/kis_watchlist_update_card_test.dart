import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/watchlist_run_result.dart';

void main() {
  testWidgets('KIS watchlist shows balanced KR update confirmation',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 1800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeKrUpdateApi();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..krWatchlist = _watchlist(['005930', '100001']);

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Update KR Top 50'), findsOneWidget);
    expect(find.text('WATCHLIST CONFIG ONLY'), findsOneWidget);
    expect(find.text('NO ORDER SUBMIT'), findsOneWidget);

    await tester.tap(find.text('Watchlist Symbols'));
    await tester.pumpAndSettle();
    expect(find.textContaining('코스피'), findsWidgets);
    expect(find.textContaining('코스닥'), findsWidgets);

    await tester.tap(find.byKey(const Key('update_kosdaq_top50_button')));
    await tester.pumpAndSettle();

    expect(find.text('Update KR Top 50'), findsWidgets);
    expect(
      find.text(
        'This will rebuild the KR watchlist as 코스피 Top 30 + 코스닥 Top 20. No order will be submitted.',
      ),
      findsOneWidget,
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Update'));
    await tester.pumpAndSettle();

    expect(api.updateCalls, 1);
    expect(controller.krWatchlist.symbols.first.symbol, '005930');
    expect(controller.latestKosdaqTop50Update?['updated'], isTrue);
    expect(find.text('코스피 Top 30 + 코스닥 Top 20'), findsOneWidget);
    expect(find.text('50 / 50'), findsOneWidget);
    expect(find.text('added 2'), findsOneWidget);
    expect(find.text('removed 1'), findsOneWidget);
    expect(find.text('kept 1'), findsOneWidget);
    expect(find.text('코스피 30 / 30'), findsOneWidget);
    expect(find.text('코스닥 20 / 20'), findsOneWidget);
    expect(find.text('50개 제한으로 일부 기존 종목이 제외되었습니다.'), findsOneWidget);
    expect(find.text('999999 - Removed - 코스닥'), findsNothing);

    await tester.tap(find.text('Excluded Symbols'));
    await tester.pumpAndSettle();
    expect(find.text('999999 - Removed - 코스닥'), findsOneWidget);

    await tester.tap(find.text('Developer Raw Payload'));
    await tester.pumpAndSettle();
    expect(find.textContaining('KOSDAQ'), findsWidgets);

    controller.dispose();
  });
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => WatchlistSection(controller: controller),
        ),
      ),
    ),
  );
}

class _FakeKrUpdateApi extends ApiClient {
  int updateCalls = 0;

  @override
  Future<Map<String, dynamic>> updateKosdaqTop50Watchlist() async {
    updateCalls += 1;
    return {
      'provider': 'kis',
      'market': 'KR',
      'source_market': 'KR',
      'source_market_label': '한국',
      'group_label': '코스피 Top 30 + 코스닥 Top 20',
      'mode': 'kr_watchlist_balanced_update_applied',
      'updated': true,
      'count': 50,
      'target_count': 50,
      'groups': [
        {
          'market': 'KOSPI',
          'market_label': '코스피',
          'target_count': 30,
          'count': 30,
        },
        {
          'market': 'KOSDAQ',
          'market_label': '코스닥',
          'target_count': 20,
          'count': 20,
        },
      ],
      'added_symbols': [
        {'symbol': '100001', 'name': 'KOSDAQ 100001', 'market': 'KOSDAQ'},
        {'symbol': '100002', 'name': 'KOSDAQ 100002', 'market': 'KOSDAQ'},
      ],
      'removed_symbols': [
        {'symbol': '999999', 'name': 'Removed', 'market': 'KOSDAQ'},
      ],
      'kept_symbols': [
        {'symbol': '005930', 'name': 'Samsung', 'market': 'KOSPI'},
      ],
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    };
  }

  @override
  Future<MarketWatchlist> fetchMarketWatchlist(String market) async {
    if (market.toUpperCase() == 'KR' && updateCalls > 0) {
      return _watchlist(['005930', '100001', '100002']);
    }
    return market.toUpperCase() == 'KR'
        ? _watchlist(['005930'])
        : MarketWatchlist.empty('US');
  }

  @override
  Future<WatchlistRunResult?> fetchLatestWatchlistRunResult() async => null;
}

MarketWatchlist _watchlist(List<String> symbols) {
  return MarketWatchlist(
    market: 'KR',
    currency: 'KRW',
    timezone: 'Asia/Seoul',
    watchlistFile: 'config/watchlist_kr.yaml',
    count: symbols.length,
    symbols: [
      for (final symbol in symbols)
        WatchlistSymbol(
          symbol: symbol,
          name: symbol == '005930' ? 'Samsung' : 'KOSDAQ $symbol',
          market: symbol == '005930' ? 'KOSPI' : 'KOSDAQ',
          marketLabel: symbol == '005930' ? '코스피' : '코스닥',
        ),
    ],
  );
}
