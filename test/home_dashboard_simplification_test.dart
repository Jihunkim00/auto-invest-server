import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_screen.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';

void main() {
  testWidgets('Home renders compact dashboard by default', (tester) async {
    final controller = _homeController();

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));
    await tester.pump();

    expect(find.text('Agent Assistant'), findsOneWidget);
    expect(find.byKey(const Key('home_compact_safety_status_bar')),
        findsOneWidget);
    expect(find.byKey(const Key('home_compact_portfolio_summary_card')),
        findsOneWidget);
    await _showHomeFinder(
      tester,
      find.byKey(const Key('home_recent_trades_compact_card')),
    );
    await _showHomeFinder(
      tester,
      find.byKey(const Key('home_advanced_details_section')),
    );
    expect(find.byKey(const Key('home_recent_trades_compact_card')),
        findsOneWidget);
    expect(find.byKey(const Key('home_advanced_details_section')),
        findsOneWidget);

    expect(find.text('Operational Readiness'), findsNothing);
    expect(find.text('Strategy Monthly Progress'), findsNothing);
    expect(find.byKey(const ValueKey('strategy-risk-state-card')),
        findsNothing);
    expect(find.byKey(const ValueKey('strategy-dry-run-auto-buy-card')),
        findsNothing);
    expect(find.byKey(const ValueKey('strategy-live-auto-buy-card')),
        findsNothing);
    expect(find.byKey(const ValueKey('strategy-live-auto-exit-card')),
        findsNothing);
    expect(find.byKey(const ValueKey('agent-chat-live-auto-buy-status-card')),
        findsNothing);
    expect(find.byKey(const ValueKey('agent-chat-live-auto-exit-status-card')),
        findsNothing);
    expect(find.byKey(const Key('automation_runtime_monitor_card')),
        findsNothing);
    expect(find.byKey(const Key('operation_rehearsal_panel')), findsNothing);
    expect(find.byKey(const Key('automation_event_timeline_card')),
        findsNothing);
    expect(find.byKey(const Key('portfolio_snapshot_section')), findsNothing);

    controller.dispose();
  });

  testWidgets('Advanced details remain available but collapsed', (tester) async {
    final controller = _homeController();

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: DashboardScreen(controller: controller)),
    ));
    await tester.pump();

    final toggle = find.byKey(const ValueKey('home-advanced-details-toggle'));
    await _showHomeFinder(tester, toggle);
    await tester.tap(toggle);
    await tester.pumpAndSettle();

    expect(find.text('Operational Readiness'), findsOneWidget);
    expect(find.byKey(const ValueKey('strategy-live-auto-buy-card')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('strategy-live-auto-exit-card')),
        findsOneWidget);
    await _showHomeFinder(
      tester,
      find.byKey(const Key('portfolio_snapshot_section')),
    );
    expect(find.byKey(const Key('portfolio_snapshot_section')), findsOneWidget);

    controller.dispose();
  });
}

DashboardController _homeController() {
  return DashboardController(_NoopApiClient(), autoload: false)
    ..activeAgentConversationKey = 'home-test'
    ..usPortfolioSummary = const PortfolioSummary(
      currency: 'USD',
      positionsCount: 1,
      pendingOrdersCount: 0,
      totalCostBasis: 1000,
      totalMarketValue: 1110,
      totalUnrealizedPl: 110,
      totalUnrealizedPlpc: 11,
      cash: 250,
      positions: [
        PositionSummary(
          symbol: 'AAPL',
          side: 'long',
          qty: 2,
          avgEntryPrice: 500,
          costBasis: 1000,
          currentPrice: 555,
          marketValue: 1110,
          unrealizedPl: 110,
          unrealizedPlpc: 11,
        ),
      ],
      pendingOrders: [],
    )
    ..automationRecentOrders = [
      _order(1, 'AAPL'),
    ];
}

OrderLogItem _order(int id, String symbol) {
  return OrderLogItem(
    id: id,
    symbol: symbol,
    side: 'buy',
    qty: 1,
    notional: 100,
    brokerOrderId: 'broker-$id',
    brokerStatus: 'filled',
    internalStatus: 'FILLED',
    createdAt: '2026-06-26T01:0${id}:00Z',
    updatedAt: '2026-06-26T01:0${id}:00Z',
  );
}

class _NoopApiClient extends ApiClient {}

Future<void> _showHomeFinder(WidgetTester tester, Finder finder) async {
  await tester.dragUntilVisible(
    finder,
    find.byKey(const Key('dashboard_home_scroll_view')),
    const Offset(0, -320),
    maxIteration: 30,
  );
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
}
