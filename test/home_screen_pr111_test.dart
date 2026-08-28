import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/core/theme/app_theme.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/home/home_screen.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';

void main() {
  testWidgets('home exposes an explicit account loading state', (tester) async {
    final controller = _controller();

    await tester.pumpWidget(_app(HomeScreen(controller: controller)));

    expect(
      find.byKey(const ValueKey('home-account-connection-status')),
      findsOneWidget,
    );
    expect(find.text('₩0'), findsNothing);
    expect(
      find.byKey(const ValueKey('home-account-connection-retry')),
      findsNothing,
    );

    controller.dispose();
  });

  testWidgets('home exposes connected state and loaded portfolio values',
      (tester) async {
    final controller = _controller()
      ..portfolioLoaded = true
      ..portfolioLoadedAt = DateTime(2026, 8, 28, 14, 30)
      ..krPortfolioSummary = _summary;

    await tester.pumpWidget(_app(HomeScreen(controller: controller)));

    expect(find.text('한국투자증권 연결됨'), findsOneWidget);
    expect(find.text('₩1734567'), findsOneWidget);
    expect(find.text('평가금액'), findsOneWidget);
    await tester.drag(find.byType(ListView), const Offset(0, -500));
    await tester.pump();
    expect(find.textContaining('삼성전자 장기 투자 포지션'), findsOneWidget);
    expect(tester.takeException(), isNull);

    controller.dispose();
  });

  testWidgets('home shows retry affordance when account loading fails',
      (tester) async {
    final controller = _controller()
      ..portfolioLoadError = 'fake broker failure';

    await tester.pumpWidget(_app(HomeScreen(controller: controller)));

    expect(
      find.byKey(const ValueKey('home-account-connection-status')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('home-account-connection-retry')),
      findsOneWidget,
    );
    expect(find.text('다시 시도'), findsOneWidget);

    controller.dispose();
  });
}

Widget _app(Widget child) {
  return MaterialApp(
    theme: AppTheme.darkTheme,
    home: child,
  );
}

DashboardController _controller() =>
    DashboardController(_FakeApiClient(), autoload: false);

const _summary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 1200000,
  totalMarketValue: 1234567,
  totalUnrealizedPl: 34567,
  totalUnrealizedPlpc: 2.88,
  cash: 500000,
  positions: [
    PositionSummary(
      symbol: '005930',
      name: '삼성전자 장기 투자 포지션',
      side: 'long',
      qty: 2,
      avgEntryPrice: 600000,
      costBasis: 1200000,
      currentPrice: 617283.5,
      marketValue: 1234567,
      unrealizedPl: 34567,
      unrealizedPlpc: 2.88,
    ),
  ],
  pendingOrders: [],
);

class _FakeApiClient extends ApiClient {
  _FakeApiClient() : super(client: _FakeHttpClient());
}

class _FakeHttpClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      Future<http.StreamedResponse>.error(
        StateError('network is intentionally unavailable in this UI test'),
      );
}
