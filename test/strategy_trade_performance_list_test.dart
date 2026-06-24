import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/strategy_trade_performance_list.dart';
import 'package:auto_invest_dashboard/models/strategy_performance.dart';

import 'strategy_performance_fixtures.dart';

void main() {
  testWidgets('trade performance list renders trade metadata and pnl',
      (tester) async {
    final performance = StrategyTradePerformanceList.fromJson(
      strategyTradePerformanceJson(),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: StrategyTradePerformanceListCard(
              performance: performance,
              loading: false,
            ),
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('strategy-trade-performance-list-card')),
      findsOneWidget,
    );
    expect(find.text('Samsung Electronics'), findsOneWidget);
    expect(find.textContaining('SELL | qty 2.0 | closed'), findsOneWidget);
    expect(find.textContaining('manual'), findsOneWidget);
    expect(find.textContaining('06-24 01:00'), findsOneWidget);
    expect(find.text('+KRW 4000'), findsOneWidget);
    expect(find.text('+2.86%'), findsOneWidget);
    expect(find.textContaining('auto buy'), findsNothing);
    expect(find.textContaining('auto sell'), findsNothing);
  });
}
