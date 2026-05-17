import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_screen.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';

void main() {
  testWidgets('Home dashboard includes Portfolio Snapshot and holdings',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..usPortfolioSummary = _usSummary
      ..krPortfolioSummary = _krSummary
      ..selectedPortfolioMarket = PortfolioMarket.kr;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => DashboardScreen(
            controller: controller,
            onOpenManualOrder: () {},
            onReviewPosition: () {},
          ),
        ),
      ),
    ));

    expect(find.text('Portfolio Snapshot'), findsOneWidget);
    expect(find.text('Current Holdings'), findsOneWidget);
    expect(find.text('005930'), findsOneWidget);
    expect(find.text('삼성전자'), findsOneWidget);
    expect(find.text('Prepare Sell Ticket'), findsOneWidget);
  });

  testWidgets('Prepare Sell Ticket on Home portfolio pre-fills manual order only',
      (tester) async {
    var openedManualOrder = false;
    final controller = DashboardController(ApiClient(), autoload: false)
      ..usPortfolioSummary = _usSummary
      ..krPortfolioSummary = _krSummary
      ..selectedPortfolioMarket = PortfolioMarket.kr;

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => DashboardScreen(
            controller: controller,
            onOpenManualOrder: () => openedManualOrder = true,
            onReviewPosition: () {},
          ),
        ),
      ),
    ));

    await tester.dragUntilVisible(
      find.text('Prepare Sell Ticket'),
      find.byType(ListView),
      const Offset(0, -300),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Prepare Sell Ticket'));
    await tester.pumpAndSettle();

    expect(openedManualOrder, isTrue);
    expect(controller.selectedOrderMarket, PortfolioMarket.kr);
    expect(controller.orderTicketSide, 'sell');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(controller.orderValidationError, isNull);
    expect(controller.orderTicketSourceMetadata?['source'], 'portfolio_position');
  });
}

const _usSummary = PortfolioSummary(
  currency: 'USD',
  positionsCount: 0,
  pendingOrdersCount: 0,
  totalCostBasis: 1000,
  totalMarketValue: 1200,
  totalUnrealizedPl: 200,
  totalUnrealizedPlpc: 0.20,
  cash: 500,
  positions: [],
  pendingOrders: [],
);

const _krSummary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 1000000,
  totalMarketValue: 1200000,
  totalUnrealizedPl: 200000,
  totalUnrealizedPlpc: 0.20,
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
      unrealizedPlpc: 0.20,
    ),
  ],
  pendingOrders: [],
);
