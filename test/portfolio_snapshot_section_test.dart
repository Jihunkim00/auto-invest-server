import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/portfolio_snapshot_section.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';

void main() {
  testWidgets('Portfolio Snapshot switches between USD and KRW summaries',
      (tester) async {
    final controller = await _pumpSnapshot(tester);

    expect(find.text('US Portfolio / Alpaca Paper'), findsOneWidget);
    expect(find.text(r'$1,000.00'), findsOneWidget);
    expect(find.text('CASH'), findsOneWidget);
    expect(find.text(r'$123.45'), findsOneWidget);
    expect(find.text('₩1,200,000'), findsNothing);
    expect(find.text('+25.00%'), findsOneWidget);

    await tester.tap(find.text('KR / KIS'));
    await tester.pumpAndSettle();

    expect(find.text('KR Portfolio / KIS Read-only'), findsOneWidget);
    expect(find.text('READ-ONLY'), findsOneWidget);
    expect(find.text('TRADING DISABLED'), findsOneWidget);
    expect(find.text('AVAILABLE CASH'), findsOneWidget);
    expect(find.text('₩30,000'), findsOneWidget);
    expect(find.text('삼성전자'), findsWidgets);
    expect(find.text('₩1,200,000'), findsWidgets);
    expect(find.text(r'$1,000.00'), findsNothing);

    controller.dispose();
  });

  testWidgets('KIS portfolio profit percent uses cost basis and P/L amount',
      (tester) async {
    final controller =
        await _pumpSnapshot(tester, krSummary: _krSmallProfitSummary);

    await tester.tap(find.text('KR / KIS'));
    await tester.pumpAndSettle();

    expect(find.text('₩9,867'), findsWidgets);
    expect(find.text('₩9,830'), findsWidgets);
    expect(find.text('+₩37'), findsWidgets);
    expect(find.text('+0.38%'), findsNWidgets(2));
    expect(find.text('+37.00%'), findsNothing);
    expect(find.text('0.00%'), findsNothing);

    controller.dispose();
  });

  testWidgets('KIS negative P/L percent uses cost basis', (tester) async {
    final controller =
        await _pumpSnapshot(tester, krSummary: _krNegativeProfitSummary);

    await tester.tap(find.text('KR / KIS'));
    await tester.pumpAndSettle();

    expect(find.text('-₩200'), findsWidgets);
    expect(find.text('-2.00%'), findsNWidgets(2));
    expect(find.text('-200.00%'), findsNothing);

    controller.dispose();
  });

  testWidgets('KIS missing cost basis displays safe percent fallback',
      (tester) async {
    final controller =
        await _pumpSnapshot(tester, krSummary: _krMissingCostSummary);

    await tester.tap(find.text('KR / KIS'));
    await tester.pumpAndSettle();

    expect(find.text('₩9,867'), findsWidgets);
    expect(find.text('+₩37'), findsWidgets);
    expect(find.text('--'), findsNWidgets(2));
    expect(find.text('+37.00%'), findsNothing);

    controller.dispose();
  });

  testWidgets('US portfolio percent display keeps raw decimal behavior',
      (tester) async {
    final controller =
        await _pumpSnapshot(tester, usSummary: _usPositionSummary);

    expect(find.text('US Portfolio / Alpaca Paper'), findsOneWidget);
    expect(find.text(r'+$12.34'), findsWidgets);
    expect(find.text('+12.34%'), findsNWidgets(2));

    controller.dispose();
  });
}

class _NoopApiClient extends ApiClient {
  _NoopApiClient({
    this.usSummary = _usSummary,
    this.krSummary = _krSummary,
  });

  final PortfolioSummary usSummary;
  final PortfolioSummary krSummary;

  @override
  Future<PortfolioSummary> fetchPortfolioSummary() async => usSummary;

  @override
  Future<PortfolioSummary> fetchUsPortfolioSummary() async => usSummary;

  @override
  Future<PortfolioSummary> fetchKrPortfolioSummary() async => krSummary;

  @override
  Future<PortfolioSummary> fetchPortfolioSummaryForMarket(String market) {
    return market.trim().toUpperCase() == 'KR'
        ? fetchKrPortfolioSummary()
        : fetchUsPortfolioSummary();
  }
}

Future<DashboardController> _pumpSnapshot(
  WidgetTester tester, {
  PortfolioSummary usSummary = _usSummary,
  PortfolioSummary krSummary = _krSummary,
}) async {
  final controller = DashboardController(
    _NoopApiClient(usSummary: usSummary, krSummary: krSummary),
    autoload: false,
  )
    ..usPortfolioSummary = usSummary
    ..krPortfolioSummary = krSummary;

  await tester.pumpWidget(MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: AnimatedBuilder(
          animation: controller,
          builder: (context, _) =>
              PortfolioSnapshotSection(controller: controller),
        ),
      ),
    ),
  ));
  return controller;
}

const _usSummary = PortfolioSummary(
  currency: 'USD',
  positionsCount: 0,
  pendingOrdersCount: 0,
  totalCostBasis: 800,
  totalMarketValue: 1000,
  totalUnrealizedPl: 200,
  totalUnrealizedPlpc: 0.25,
  cash: 123.45,
  positions: [],
  pendingOrders: [],
);

const _usPositionSummary = PortfolioSummary(
  currency: 'USD',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 100,
  totalMarketValue: 112.34,
  totalUnrealizedPl: 12.34,
  totalUnrealizedPlpc: 0.1234,
  cash: 123.45,
  positions: [
    PositionSummary(
      symbol: 'AAPL',
      name: 'Apple',
      side: 'long',
      qty: 1,
      avgEntryPrice: 100,
      costBasis: 100,
      currentPrice: 112.34,
      marketValue: 112.34,
      unrealizedPl: 12.34,
      unrealizedPlpc: 0.1234,
    ),
  ],
  pendingOrders: [],
);

const _krSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 1,
  totalCostBasis: 1000000,
  totalMarketValue: 1200000,
  totalUnrealizedPl: 200000,
  totalUnrealizedPlpc: 0.2,
  cash: 30000,
  positions: [
    PositionSummary(
      symbol: '005930',
      name: '삼성전자',
      side: 'long',
      qty: 2,
      avgEntryPrice: 500000,
      costBasis: 1000000,
      currentPrice: 600000,
      marketValue: 1200000,
      unrealizedPl: 200000,
      unrealizedPlpc: 0.2,
    ),
  ],
  pendingOrders: [
    PendingOrderSummary(
      id: 'order-1',
      symbol: '005930',
      name: '삼성전자',
      side: 'buy',
      type: '',
      status: 'pending',
      qty: 1,
      unfilledQty: 1,
      notional: null,
      limitPrice: null,
      price: 600000,
      estimatedAmount: 600000,
      submittedAt: '09:30:00',
    ),
  ],
);

const _krSmallProfitSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 9830,
  totalMarketValue: 9867,
  totalUnrealizedPl: 37,
  totalUnrealizedPlpc: 0,
  cash: 30000,
  positions: [
    PositionSummary(
      symbol: '091810',
      name: 'Small Profit',
      side: 'long',
      qty: 11,
      avgEntryPrice: 893.64,
      costBasis: 9830,
      currentPrice: 897,
      marketValue: 9867,
      unrealizedPl: 37,
      unrealizedPlpc: 37,
    ),
  ],
  pendingOrders: [],
);

const _krNegativeProfitSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 10000,
  totalMarketValue: 9800,
  totalUnrealizedPl: -200,
  totalUnrealizedPlpc: 0,
  cash: 30000,
  positions: [
    PositionSummary(
      symbol: '091810',
      name: 'Small Loss',
      side: 'long',
      qty: 10,
      avgEntryPrice: 1000,
      costBasis: 10000,
      currentPrice: 980,
      marketValue: 9800,
      unrealizedPl: -200,
      unrealizedPlpc: -200,
    ),
  ],
  pendingOrders: [],
);

const _krMissingCostSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 0,
  totalMarketValue: 9867,
  totalUnrealizedPl: 37,
  totalUnrealizedPlpc: 37,
  cash: 30000,
  positions: [
    PositionSummary(
      symbol: '091810',
      name: 'Missing Cost',
      side: 'long',
      qty: 11,
      avgEntryPrice: 0,
      costBasis: 0,
      currentPrice: 897,
      marketValue: 9867,
      unrealizedPl: 37,
      unrealizedPlpc: 37,
    ),
  ],
  pendingOrders: [],
);
