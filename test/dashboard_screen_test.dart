import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_screen.dart';
import 'package:auto_invest_dashboard/models/managed_position.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';

class FakeKisApiClient extends ApiClient {
  @override
  Future<ManualSellPreparation> prepareKisManualSell(String symbol) async {
    return const ManualSellPreparation(
      provider: 'kis',
      market: 'KR',
      symbol: '005930',
      companyName: 'Samsung Electronics',
      quantity: 1,
      currentPrice: 600000,
      estimatedAmount: 600000,
      exitReason: 'stop_loss_triggered',
      humanReason: 'Stop loss triggered',
      holdingStatus: 'SELL_READY',
      canPrepare: true,
      canSubmit: true,
      blockReasons: [],
      sourceMetadata: {'source': 'portfolio_position'},
      rawPayload: {'symbol': '005930'},
    );
  }
}

const _krManagedPosition = ManagedPosition(
  provider: 'kis',
  market: 'KR',
  symbol: '005930',
  companyName: 'Samsung Electronics',
  quantity: 1,
  averagePrice: 500000,
  costBasis: 1000000,
  currentPrice: 600000,
  currentValue: 1200000,
  unrealizedPl: 200000,
  unrealizedPlPct: 0.20,
  holdingStatus: 'SELL_READY',
  exitReason: 'stop_loss_triggered',
  humanReason: 'Stop loss triggered',
  stopLossTriggered: true,
  takeProfitTriggered: false,
  weakTrendTriggered: false,
  sellPressureTriggered: false,
  manualReviewRequired: true,
  finalSellScore: 73.5,
  finalBuyScore: 10.1,
  quantSellScore: 80.0,
  quantBuyScore: 18.2,
  aiSellScore: 75.0,
  aiBuyScore: 5.0,
  confidence: 92.0,
  technicalSnapshot: {},
  riskFlags: [],
  gatingNotes: [],
  blockReasons: [],
  canPrepareManualSell: true,
  canSubmitManualSell: true,
  latestManualSellOrder: null,
  rawPayload: {},
);

void main() {
  testWidgets('Home dashboard includes Portfolio Snapshot and holdings',
      (tester) async {
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..usPortfolioSummary = _usSummary
      ..krPortfolioSummary = _krSummary
      ..kisManagedPositions = const [_krManagedPosition]
      ..selectedProvider = SelectedProvider.kis
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
    expect(find.byKey(const ValueKey('portfolio-position-card-005930')),
        findsOneWidget);
    expect(find.textContaining('005930 · Samsung Electronics'), findsOneWidget);
    expect(find.textContaining('Samsung Electronics'), findsOneWidget);
  });

  testWidgets(
      'Prepare Sell Ticket on Home portfolio pre-fills manual order only',
      (tester) async {
    var openedManualOrder = false;
    final controller = DashboardController(FakeKisApiClient(), autoload: false)
      ..usPortfolioSummary = _usSummary
      ..krPortfolioSummary = _krSummary
      ..kisManagedPositions = const [_krManagedPosition]
      ..selectedProvider = SelectedProvider.kis
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

    await tester.ensureVisible(
      find.textContaining('005930 · Samsung Electronics'),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.textContaining('005930 · Samsung Electronics'));
    await tester.pumpAndSettle();

    final prepareSellButton =
        find.byKey(const ValueKey('prepare-manual-sell-005930'));
    await tester.ensureVisible(prepareSellButton);
    await tester.pumpAndSettle();

    expect(prepareSellButton, findsOneWidget);
    await tester.tap(prepareSellButton);
    await tester.pumpAndSettle();

    expect(openedManualOrder, isTrue);
    expect(controller.selectedOrderMarket, PortfolioMarket.kr);
    expect(controller.orderTicketSide, 'sell');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(controller.orderValidationError, isNull);
    expect(
        controller.orderTicketSourceMetadata?['source'], 'portfolio_position');
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
