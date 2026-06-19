import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_tool_result_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_tool_result.dart';

void main() {
  testWidgets('Price result card renders title value and badges', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AgentChatToolResultCardList(
            cards: [
              AgentChatResultCard(
                cardType: 'price',
                title: 'Samsung Electronics current price',
                subtitle: '005930 · KIS',
                primaryValue: '₩72,000',
                badges: ['READ ONLY', 'NO ORDER'],
                rows: [],
                data: {'symbol': '005930'},
              ),
            ],
            followUpSuggestions: ['Analyze this'],
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('agent-chat-result-card-price')),
      findsOneWidget,
    );
    expect(find.text('Samsung Electronics current price'), findsOneWidget);
    expect(find.text('₩72,000'), findsOneWidget);
    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.text('NO ORDER'), findsOneWidget);
    expect(find.text('Analyze this'), findsOneWidget);
  });
}
