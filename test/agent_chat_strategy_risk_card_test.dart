import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_tool_result_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_tool_result.dart';

void main() {
  testWidgets('agent chat renders specialized strategy risk card',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AgentChatToolResultCardList(
            cards: [
              AgentChatResultCard(
                cardType: 'strategy_entry_risk',
                title: 'Target-Aware Risk',
                subtitle: 'BALANCED',
                primaryValue: '₩20,000',
                badges: [
                  'ENTRY ALLOWED',
                  'SIZE REDUCED',
                  'READ ONLY',
                  'NO ORDER SUBMIT',
                ],
                rows: [
                  {'label': 'Block reason', 'value': '-'},
                  {
                    'label': 'Risk flags',
                    'value': 'near_monthly_target_size_reduced'
                  },
                ],
                data: {'approved': true, 'action': 'reduce'},
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
          'agent-chat-strategy-risk-card-strategy_entry_risk',
        ),
      ),
      findsOneWidget,
    );
    expect(find.text('Target-Aware Risk'), findsOneWidget);
    expect(find.text('ENTRY ALLOWED'), findsOneWidget);
    expect(find.text('SIZE REDUCED'), findsOneWidget);
    expect(find.text('Submit Order'), findsNothing);
    expect(find.text('Auto Buy Now'), findsNothing);
  });
}
