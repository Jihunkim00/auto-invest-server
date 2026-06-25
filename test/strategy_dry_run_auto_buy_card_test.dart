import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/strategy_dry_run_auto_buy_card.dart';
import 'package:auto_invest_dashboard/models/strategy_dry_run_auto_buy.dart';

import 'strategy_dry_run_auto_buy_model_test.dart';

void main() {
  testWidgets('dashboard card renders dry-run result and safe controls',
      (tester) async {
    var runCalls = 0;
    var refreshCalls = 0;
    final result = StrategyDryRunAutoBuyResult.fromJson(dryRunResultJson());

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: StrategyDryRunAutoBuyCard(
              result: result,
              loading: false,
              error: null,
              onRun: () async {
                runCalls += 1;
                return const ActionResult(success: true, message: 'ran');
              },
              onRefresh: () async {
                refreshCalls += 1;
                return const ActionResult(success: true, message: 'refreshed');
              },
            ),
          ),
        ),
      ),
    );

    expect(find.text('DRY RUN ONLY'), findsOneWidget);
    expect(find.textContaining('005930'), findsOneWidget);
    expect(find.textContaining('dry_run_only'), findsOneWidget);
    expect(find.text('Run Dry-Run Auto Buy Once'), findsOneWidget);
    expect(find.text('Refresh Recent Dry-Runs'), findsOneWidget);
    expect(find.text('Submit Order'), findsNothing);
    expect(find.text('Confirm Live Order'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('strategy-dry-run-run-once')));
    await tester.pump();
    expect(runCalls, 1);

    await tester.tap(find.byKey(const ValueKey('strategy-dry-run-refresh')));
    await tester.pump();
    expect(refreshCalls, 1);
  });

  testWidgets('error state renders retry', (tester) async {
    var retryCalls = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: StrategyDryRunAutoBuyCard(
            result: null,
            loading: false,
            error: 'dry-run unavailable',
            onRun: () async =>
                const ActionResult(success: false, message: 'failed'),
            onRefresh: () async {
              retryCalls += 1;
              return const ActionResult(success: true, message: 'retried');
            },
          ),
        ),
      ),
    );

    expect(find.text('dry-run unavailable'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('strategy-dry-run-retry')));
    await tester.pump();
    expect(retryCalls, 1);
  });
}
