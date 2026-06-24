import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_tool_result_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_tool_result.dart';

void main() {
  testWidgets('agent chat renders specialized performance result card',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AgentChatToolResultCardList(
            cards: [
              AgentChatResultCard(
                cardType: 'strategy_monthly_performance',
                title: 'Monthly performance',
                subtitle: '2026-06 | balanced',
                primaryValue: '+2.00%',
                badges: ['READ ONLY', 'ESTIMATED', 'NO ORDER'],
                rows: [
                  {'label': 'Target progress', 'value': '66.7%'},
                  {'label': 'Loss budget used', 'value': '0.0%'},
                ],
                data: {'target_hit': false},
              ),
            ],
            followUpSuggestions: [],
          ),
        ),
      ),
    );

    expect(
      find.byKey(
        const ValueKey(
          'agent-chat-performance-card-strategy_monthly_performance',
        ),
      ),
      findsOneWidget,
    );
    expect(find.text('Monthly performance'), findsOneWidget);
    expect(find.text('+2.00%'), findsOneWidget);
    expect(find.text('66.7%'), findsOneWidget);
    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.textContaining('auto buy'), findsNothing);
    expect(find.textContaining('auto sell'), findsNothing);
    expect(
      find.byKey(
        const ValueKey(
          'agent-chat-result-card-strategy_monthly_performance',
        ),
      ),
      findsNothing,
    );
  });
}
