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
                subtitle: '005930 · KIS',
                primaryValue: '₩72,000',
                badges: ['READ ONLY', 'KIS', 'NO ORDER', 'NO VALIDATION'],
                rows: [
                  {'label': 'lookup', 'value': 'read-only lookup'},
                  {'label': 'order', 'value': 'no order submitted'},
                ],
                data: {'symbol': '005930'},
              ),
            ],
            followUpSuggestions: ['이 종목 분석해줘'],
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('agent-chat-result-card-price')),
      findsOneWidget,
    );
    expect(find.text('삼성전자 현재가'), findsOneWidget);
    expect(find.text('005930 · KIS'), findsOneWidget);
    expect(find.text('₩72,000'), findsOneWidget);
    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.text('NO ORDER'), findsOneWidget);
    expect(find.text('NO VALIDATION'), findsOneWidget);
    expect(find.text('read-only lookup'), findsOneWidget);
    expect(find.text('no order submitted'), findsOneWidget);
    expect(find.text('이 종목 분석해줘'), findsOneWidget);
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
                title: 'System Status',
                badges: ['READ ONLY', 'NO SETTINGS CHANGE'],
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
    expect(find.text('System Status'), findsOneWidget);
    expect(find.text('dry_run'), findsOneWidget);
    expect(find.text('ON'), findsOneWidget);
    expect(find.text('kill_switch'), findsOneWidget);
    expect(find.text('OFF'), findsOneWidget);
    expect(find.text('NO SETTINGS CHANGE'), findsOneWidget);
  });

  testWidgets('Long Korean answer card rows do not overflow', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 260,
            child: AgentChatToolResultCardList(
              cards: [
                AgentChatResultCard(
                  cardType: 'positions',
                  title: '보유종목',
                  subtitle: 'KIS',
                  primaryValue: '1개 종목',
                  badges: ['READ ONLY', 'NO ORDER', 'NO VALIDATION'],
                  rows: [
                    {
                      'label': '삼성전자 매우 긴 테스트 라벨',
                      'value':
                          'qty 1 · value 72000 · P/L 1500 · read-only lookup',
                    },
                  ],
                  data: {'symbol': '005930'},
                ),
              ],
              followUpSuggestions: ['최근 주문 기록 보여줘'],
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('보유종목'), findsOneWidget);
    expect(find.text('최근 주문 기록 보여줘'), findsOneWidget);
  });
}
