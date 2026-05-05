import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/portfolio_snapshot_section.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';

void main() {
  testWidgets('Portfolio Snapshot switches between USD and KRW summaries',
      (tester) async {
    final controller = DashboardController(_NoopApiClient(), autoload: false)
      ..usPortfolioSummary = _usSummary
      ..krPortfolioSummary = _krSummary;

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

    expect(find.text('US Portfolio / Alpaca Paper'), findsOneWidget);
    expect(find.text(r'$1,000.00'), findsOneWidget);
    expect(find.text('Cash'), findsOneWidget);
    expect(find.text(r'$123.45'), findsOneWidget);
    expect(find.text('₩1,200,000'), findsNothing);

    await tester.tap(find.text('KR / KIS'));
    await tester.pumpAndSettle();

    expect(find.text('KR Portfolio / KIS Read-only'), findsOneWidget);
    expect(find.text('READ-ONLY'), findsOneWidget);
    expect(find.text('TRADING DISABLED'), findsOneWidget);
    expect(find.text('Available Cash'), findsOneWidget);
    expect(find.text('₩30,000'), findsOneWidget);
    expect(find.text('삼성전자'), findsWidgets);
    expect(find.text('₩1,200,000'), findsWidgets);
    expect(find.text(r'$1,000.00'), findsNothing);

    controller.dispose();
  });
}

class _NoopApiClient extends ApiClient {
  @override
  Future<PortfolioSummary> fetchPortfolioSummary() async => _usSummary;

  @override
  Future<PortfolioSummary> fetchUsPortfolioSummary() async => _usSummary;

  @override
  Future<PortfolioSummary> fetchKrPortfolioSummary() async => _krSummary;

  @override
  Future<PortfolioSummary> fetchPortfolioSummaryForMarket(String market) {
    return market.trim().toUpperCase() == 'KR'
        ? fetchKrPortfolioSummary()
        : fetchUsPortfolioSummary();
  }
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
