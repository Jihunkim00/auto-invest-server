import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_tool_result_card.dart';
import 'package:auto_invest_dashboard/models/agent_chat_tool_result.dart';

void main() {
  testWidgets('Price result card renders title value and badges',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AgentChatToolResultCardList(
            cards: [
              AgentChatResultCard(
                cardType: 'price',
                title: '삼성전자 현재가',
                subtitle: '005930 / KIS',
                primaryValue: 'KRW 72,000',
                badges: ['READ ONLY', 'NO ORDER'],
                rows: [],
                data: {'symbol': '005930'},
              ),
            ],
            followUpSuggestions: ['이 종목을 간단히 분석해줄까요?'],
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('agent-chat-result-card-price')),
      findsOneWidget,
    );
    expect(find.text('삼성전자 현재가'), findsOneWidget);
    expect(find.text('KRW 72,000'), findsOneWidget);
    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.text('NO ORDER'), findsOneWidget);
    expect(find.text('이 종목을 간단히 분석해줄까요?'), findsOneWidget);
  });

  testWidgets('Settings result card renders rows and no-change badge',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AgentChatToolResultCardList(
            cards: [
              AgentChatResultCard(
                cardType: 'settings',
                title: 'Safety Status',
                badges: ['READ ONLY', 'NO CHANGE'],
                rows: [
                  {'label': 'dry_run', 'value': 'ON'},
                  {'label': 'kill_switch', 'value': 'OFF'},
                ],
                data: {'dry_run': true, 'kill_switch': false},
              ),
            ],
            followUpSuggestions: [],
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('agent-chat-result-card-settings')),
      findsOneWidget,
    );
    expect(find.text('Safety Status'), findsOneWidget);
    expect(find.text('dry_run'), findsOneWidget);
    expect(find.text('ON'), findsOneWidget);
    expect(find.text('kill_switch'), findsOneWidget);
    expect(find.text('OFF'), findsOneWidget);
    expect(find.text('NO CHANGE'), findsOneWidget);
  });
}
