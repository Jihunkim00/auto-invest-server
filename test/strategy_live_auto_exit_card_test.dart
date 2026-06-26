import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/strategy_live_auto_exit_card.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_exit.dart';

import 'strategy_live_auto_exit_model_test.dart';

void main() {
  testWidgets('guarded live exit card renders safety badges and confirmation',
      (tester) async {
    var runCalls = 0;
    var refreshCalls = 0;
    final readiness = StrategyLiveAutoExitReadiness.fromJson(
      liveExitReadinessJson(ready: true),
    );
    final latest = StrategyLiveAutoExitRunResult.fromJson(
      liveExitRunResultJson(status: 'submitted', submitted: true),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: StrategyLiveAutoExitCard(
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

    expect(find.text('LIVE AUTO EXIT'), findsOneWidget);
    expect(find.text('DISABLED BY DEFAULT'), findsOneWidget);
    expect(find.text('HELD POSITIONS ONLY'), findsOneWidget);
    expect(find.text('STOP LOSS FIRST'), findsOneWidget);
    expect(find.text('KIS VALIDATION REQUIRED'), findsOneWidget);
    expect(find.text('ONE SHOT ONLY'), findsOneWidget);
    expect(find.text('NO SCHEDULER'), findsOneWidget);
    expect(find.text('NO AUTO RETRY'), findsOneWidget);
    expect(find.text('Refresh Exit Readiness'), findsOneWidget);
    expect(find.text('Run Guarded Auto Exit Once'), findsOneWidget);
    expect(find.text('Enable Scheduler'), findsNothing);
    expect(find.text('Turn Off Dry Run'), findsNothing);
    expect(find.text('Disable Kill Switch'), findsNothing);
    expect(find.text('Enable KIS Real Order'), findsNothing);
    expect(find.text('Retry Submit'), findsNothing);
    expect(find.text('Submit Again'), findsNothing);
    expect(find.text('Buy'), findsNothing);

    await tester
        .tap(find.byKey(const ValueKey('strategy-live-auto-exit-run-once')));
    await tester.pumpAndSettle();
    expect(
      find.text(
        '이 작업은 실제 KIS 매도 주문을 제출할 수 있습니다. 보유 포지션, 손절/익절 기준, KIS validation을 다시 확인하고 통과할 때만 주문합니다. 계속할까요?',
      ),
      findsOneWidget,
    );
    expect(runCalls, 0);

    await tester
        .tap(find.byKey(const ValueKey('strategy-live-auto-exit-confirm-run')));
    await tester.pumpAndSettle();
    expect(runCalls, 1);

    await tester
        .tap(find.byKey(const ValueKey('strategy-live-auto-exit-refresh')));
    await tester.pumpAndSettle();
    expect(refreshCalls, 1);
  });

  testWidgets('guarded live exit run button is disabled when blocked',
      (tester) async {
    var runCalls = 0;
    final readiness = StrategyLiveAutoExitReadiness.fromJson(
      liveExitReadinessJson(ready: false),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: StrategyLiveAutoExitCard(
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
      find.byKey(const ValueKey('strategy-live-auto-exit-run-once')),
    );
    expect(button.onPressed, isNull);
    expect(runCalls, 0);
  });
}
