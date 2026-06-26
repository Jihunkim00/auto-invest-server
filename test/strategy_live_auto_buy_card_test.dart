import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/strategy_live_auto_buy_card.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_buy.dart';

import 'strategy_live_auto_buy_model_test.dart';

void main() {
  testWidgets('guarded live card renders safety badges and confirmation',
      (tester) async {
    var runCalls = 0;
    var refreshCalls = 0;
    final readiness = StrategyLiveAutoBuyReadiness.fromJson(
      liveReadinessJson(ready: true),
    );
    final latest = StrategyLiveAutoBuyRunResult.fromJson(
      liveRunResultJson(status: 'submitted', submitted: true),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: StrategyLiveAutoBuyCard(
              readiness: readiness,
              latest: latest,
              recent: [latest],
              loading: false,
              error: null,
              onRun: () async {
                runCalls += 1;
                return const ActionResult(success: true, message: 'submitted');
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

    expect(find.text('LIVE AUTO BUY'), findsOneWidget);
    expect(find.text('DISABLED BY DEFAULT'), findsOneWidget);
    expect(find.text('REQUIRES RECENT DRY RUN'), findsOneWidget);
    expect(find.text('TARGET RISK GATED'), findsOneWidget);
    expect(find.text('KIS VALIDATION REQUIRED'), findsOneWidget);
    expect(find.text('ONE SHOT ONLY'), findsOneWidget);
    expect(find.text('NO SCHEDULER'), findsOneWidget);
    expect(find.text('NO AUTO RETRY'), findsOneWidget);
    expect(find.text('Enable Scheduler'), findsNothing);
    expect(find.text('Turn Off Dry Run'), findsNothing);
    expect(find.text('Disable Kill Switch'), findsNothing);
    expect(find.text('Enable KIS Real Order'), findsNothing);
    expect(find.text('Retry Submit'), findsNothing);
    expect(find.text('Submit Again'), findsNothing);

    await tester
        .tap(find.byKey(const ValueKey('strategy-live-auto-buy-run-once')));
    await tester.pumpAndSettle();
    expect(find.textContaining('실제 KIS 매수 주문'), findsOneWidget);
    expect(runCalls, 0);

    await tester
        .tap(find.byKey(const ValueKey('strategy-live-auto-buy-confirm-run')));
    await tester.pumpAndSettle();
    expect(runCalls, 1);

    await tester
        .tap(find.byKey(const ValueKey('strategy-live-auto-buy-refresh')));
    await tester.pumpAndSettle();
    expect(refreshCalls, 1);
  });

  testWidgets('guarded live run button is disabled when blocked',
      (tester) async {
    var runCalls = 0;
    final readiness = StrategyLiveAutoBuyReadiness.fromJson(
      liveReadinessJson(ready: false),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: StrategyLiveAutoBuyCard(
            readiness: readiness,
            latest: null,
            recent: const [],
            loading: false,
            error: null,
            onRun: () async {
              runCalls += 1;
              return const ActionResult(success: true, message: 'ran');
            },
            onRefresh: () async =>
                const ActionResult(success: true, message: 'refreshed'),
          ),
        ),
      ),
    );

    final button = tester.widget<FilledButton>(
      find.byKey(const ValueKey('strategy-live-auto-buy-run-once')),
    );
    expect(button.onPressed, isNull);
    expect(runCalls, 0);
  });
}
