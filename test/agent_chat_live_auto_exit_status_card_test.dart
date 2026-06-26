import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_live_auto_exit_status_card.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_exit.dart';

import 'strategy_live_auto_exit_model_test.dart';

void main() {
  testWidgets('agent chat live auto exit card is read only', (tester) async {
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
          body: AgentChatLiveAutoExitStatusCard(
            readiness: readiness,
            recent: [latest],
            loading: false,
            error: null,
            onRefresh: () async {
              refreshCalls += 1;
              return const ActionResult(success: true, message: 'refreshed');
            },
          ),
        ),
      ),
    );

    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.text('LIVE AUTO EXIT'), findsOneWidget);
    expect(find.text('HELD POSITIONS ONLY'), findsOneWidget);
    expect(find.text('NO CHAT EXECUTION'), findsOneWidget);
    expect(find.text('NO VALIDATION'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsOneWidget);
    expect(find.text('Run Guarded Auto Exit Once'), findsNothing);
    expect(find.byKey(const ValueKey('strategy-live-auto-exit-run-once')),
        findsNothing);

    await tester
        .tap(find.byKey(const ValueKey('agent-chat-live-auto-exit-refresh')));
    await tester.pumpAndSettle();
    expect(refreshCalls, 1);
  });
}
