import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_screen.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';

void main() {
  testWidgets('Recent trades compact card caps rows and opens Logs',
      (tester) async {
    var openedLogs = false;
    final controller = DashboardController(_NoopApiClient(), autoload: false)
      ..activeAgentConversationKey = 'recent-test'
      ..automationRecentOrders = [
        _order(1, 'AAPL'),
        _order(2, 'MSFT'),
        _order(3, 'NVDA'),
        _order(4, 'TSLA'),
      ];

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: DashboardScreen(
          controller: controller,
          onOpenLogs: () => openedLogs = true,
        ),
      ),
    ));
    await tester.pump();

    await _showHomeFinder(
      tester,
      find.byKey(const Key('home_recent_trades_compact_card')),
    );
    expect(find.byKey(const Key('home_recent_trades_compact_card')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('home-recent-compact-item-0')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('home-recent-compact-item-1')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('home-recent-compact-item-2')),
        findsOneWidget);
    expect(
        find.byKey(const ValueKey('home-recent-compact-item-3')), findsNothing);
    expect(find.textContaining('AAPL'), findsOneWidget);
    expect(find.textContaining('MSFT'), findsOneWidget);
    expect(find.textContaining('NVDA'), findsOneWidget);
    expect(find.textContaining('TSLA'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('home-view-all-logs')));
    await tester.pumpAndSettle();

    expect(openedLogs, isTrue);
    controller.dispose();
  });
}

OrderLogItem _order(int id, String symbol) {
  return OrderLogItem(
    id: id,
    symbol: symbol,
    side: id.isEven ? 'sell' : 'buy',
    qty: id.toDouble(),
    notional: 1000.0 + id,
    brokerOrderId: 'broker-$id',
    brokerStatus: 'filled',
    internalStatus: 'FILLED',
    createdAt: '2026-06-26T01:0$id:00Z',
    updatedAt: '2026-06-26T01:0$id:00Z',
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
