import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/strategy_monthly_progress_card.dart';
import 'package:auto_invest_dashboard/models/strategy_performance.dart';

import 'strategy_performance_fixtures.dart';

void main() {
  testWidgets('monthly progress card renders targets and safety state',
      (tester) async {
    final performance = StrategyMonthlyPerformance.fromJson(
      strategyMonthlyPerformanceJson(),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: StrategyMonthlyProgressCard(
              performance: performance,
              loading: false,
              error: null,
              onRefresh: () async => const ActionResult(
                success: true,
                message: 'refreshed',
              ),
            ),
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('strategy-monthly-progress-card')),
      findsOneWidget,
    );
    expect(find.text('Strategy Monthly Progress'), findsOneWidget);
    expect(find.textContaining('Balanced'), findsOneWidget);
    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.text('66.7%'), findsOneWidget);
    expect(find.text('+2.00%'), findsOneWidget);
    expect(find.text('0.0%'), findsOneWidget);
    expect(find.text('ALLOWED'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    expect(find.textContaining('auto buy'), findsNothing);
    expect(find.textContaining('auto sell'), findsNothing);
  });

  testWidgets('monthly progress card renders data quality warning',
      (tester) async {
    final payload = strategyMonthlyPerformanceJson()
      ..['data_quality'] = strategyDataQualityJson(
        hasCompleteFills: false,
        unmatchedOrdersCount: 1,
        notes: const ['unmatched_sell'],
      );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: StrategyMonthlyProgressCard(
              performance: StrategyMonthlyPerformance.fromJson(payload),
              loading: false,
              error: null,
              onRefresh: () async => const ActionResult(
                success: true,
                message: 'refreshed',
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.textContaining('Data quality'), findsOneWidget);
    expect(find.textContaining('unmatched_sell'), findsOneWidget);
  });
}
