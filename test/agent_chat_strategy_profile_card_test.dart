import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_tool_result_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_tool_result.dart';

void main() {
  testWidgets('strategy profile result card renders badges and rows',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AgentChatToolResultCardList(
            cards: [
              AgentChatResultCard(
                cardType: 'strategy_profile',
                title: 'Strategy profiles',
                subtitle: 'active: 보통형',
                primaryValue: '3.0%-5.0%',
                badges: [
                  'READ ONLY',
                  'PROFILE ONLY',
                  'NO ORDER SUBMIT',
                  'NO VALIDATION',
                  'NO SCHEDULER CHANGE',
                ],
                rows: [
                  {'label': '보통형', 'value': 'monthly target 3.0%-5.0%'},
                  {'label': '고수익형', 'value': 'monthly target 5.0%-8.0%'},
                ],
                data: {'active_profile': 'balanced'},
              ),
            ],
            followUpSuggestions: ['고수익형으로 바꾸면?'],
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('agent-chat-result-card-strategy_profile')),
      findsOneWidget,
    );
    expect(find.text('Strategy profiles'), findsOneWidget);
    expect(find.text('PROFILE ONLY'), findsOneWidget);
    expect(find.text('NO ORDER SUBMIT'), findsOneWidget);
    expect(find.text('NO VALIDATION'), findsOneWidget);
    expect(find.text('NO SCHEDULER CHANGE'), findsOneWidget);
    expect(find.text('monthly target 5.0%-8.0%'), findsOneWidget);
    expect(find.text('고수익형으로 바꾸면?'), findsOneWidget);
  });
}
