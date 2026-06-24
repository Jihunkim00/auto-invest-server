import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/strategy_daily_pnl_card.dart';
import 'package:auto_invest_dashboard/models/strategy_performance.dart';

import 'strategy_performance_fixtures.dart';

void main() {
  testWidgets('daily pnl card renders realized and estimated values',
      (tester) async {
    final performance =
        StrategyDailyPerformance.fromJson(strategyDailyPerformanceJson());

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: StrategyDailyPnlCard(
              performance: performance,
              loading: false,
              error: null,
            ),
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('strategy-daily-pnl-card')),
      findsOneWidget,
    );
    expect(find.text('Today P&L'), findsOneWidget);
    expect(find.text('+12000 KRW'), findsOneWidget);
    expect(find.text('-2000 KRW'), findsOneWidget);
    expect(find.text('+9500 KRW'), findsOneWidget);
    expect(find.text('+1.90%'), findsOneWidget);
    expect(find.text('NO ORDER'), findsOneWidget);
    expect(find.textContaining('auto buy'), findsNothing);
    expect(find.textContaining('auto sell'), findsNothing);
  });
}
