import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_live_auto_buy_status_card.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_buy.dart';

import 'strategy_live_auto_buy_model_test.dart';

void main() {
  testWidgets('agent chat live auto buy card is read only', (tester) async {
    var refreshCalls = 0;
    final readiness = StrategyLiveAutoBuyReadiness.fromJson(
      liveReadinessJson(ready: false),
    );
    final latest = StrategyLiveAutoBuyRunResult.fromJson(
      liveRunResultJson(action: 'blocked', blockReason: 'dry_run_enabled'),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentChatLiveAutoBuyStatusCard(
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

    expect(find.text('Agent Chat Live Auto Buy Status'), findsOneWidget);
    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.text('NO CHAT EXECUTION'), findsOneWidget);
    expect(find.text('NO VALIDATION'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsOneWidget);
    expect(find.text('Run Guarded Live Buy Once'), findsNothing);
    expect(find.text('Enable Scheduler'), findsNothing);
    expect(find.text('Retry Submit'), findsNothing);
    expect(find.text('Submit Again'), findsNothing);

    await tester
        .tap(find.byKey(const ValueKey('agent-chat-live-auto-buy-refresh')));
    await tester.pumpAndSettle();
    expect(refreshCalls, 1);
  });
}
