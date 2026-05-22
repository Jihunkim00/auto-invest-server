import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/watchlist_run_result.dart';

void main() {
  testWidgets('KIS watchlist shows KOSDAQ top 50 update confirmation',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 1800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeKosdaqUpdateApi();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..krWatchlist = _watchlist(['005930']);

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Update KOSDAQ Top 50'), findsOneWidget);
    expect(find.text('WATCHLIST CONFIG ONLY'), findsOneWidget);
    expect(find.text('NO ORDER SUBMIT'), findsOneWidget);

    await tester.tap(find.byKey(const Key('update_kosdaq_top50_button')));
    await tester.pumpAndSettle();

    expect(find.text('Update KOSDAQ Top 50'), findsWidgets);
    expect(
      find.text(
        'This will replace the KR watchlist with KOSDAQ top 50 by market cap. No order will be submitted.',
      ),
      findsOneWidget,
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Update'));
    await tester.pumpAndSettle();

    expect(api.updateCalls, 1);
    expect(controller.krWatchlist.symbols.first.symbol, '100001');
    expect(controller.latestKosdaqTop50Update?['updated'], isTrue);

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

class _FakeKosdaqUpdateApi extends ApiClient {
  int updateCalls = 0;

  @override
  Future<Map<String, dynamic>> updateKosdaqTop50Watchlist() async {
    updateCalls += 1;
    return {
      'provider': 'kis',
      'market': 'KR',
      'source_market': 'KOSDAQ',
      'mode': 'watchlist_update_applied',
      'updated': true,
      'count': 50,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    };
  }

  @override
  Future<MarketWatchlist> fetchMarketWatchlist(String market) async {
    if (market.toUpperCase() == 'KR' && updateCalls > 0) {
      return _watchlist(['100001', '100002']);
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
            symbol: symbol, name: 'KOSDAQ $symbol', market: 'KOSDAQ'),
    ],
  );
}
