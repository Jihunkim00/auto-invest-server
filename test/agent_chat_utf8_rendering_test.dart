import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_full_panel.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';

void main() {
  testWidgets('Korean Agent Chat answer and card render without mojibake',
      (tester) async {
    final controller = DashboardController(_NoopApiClient(), autoload: false)
      ..agentChatMode = AgentChatPanelMode.fullscreen
      ..activeAgentConversationKey = 'conv_utf8'
      ..agentMessages = [
        AgentChatMessage(
          id: 'answer',
          role: AgentChatRole.assistant,
          text:
              '삼성전자(005930)는 KIS 기준 현재가가 ₩72,000입니다. 주문·validation·confirm_live는 실행하지 않았습니다.',
          createdAt: DateTime.utc(2026, 6, 19),
          status: AgentChatStatus.sent,
          safetyBadges: const [
            'READ ONLY',
            'KIS',
            'NO ORDER',
            'NO VALIDATION',
            'NO SETTINGS CHANGE',
          ],
          metadata: const {
            'result_cards': [
              {
                'card_type': 'price',
                'title': '삼성전자 현재가',
                'subtitle': '005930 · KIS',
                'primary_value': '₩72,000',
                'badges': ['READ ONLY', 'KIS', 'NO ORDER', 'NO VALIDATION'],
                'rows': [
                  {'label': 'lookup', 'value': 'read-only lookup'},
                  {'label': 'order', 'value': 'no order submitted'},
                ],
                'data': {'symbol': '005930'},
              }
            ],
            'follow_up_suggestions': ['이 종목 분석해줘', '보유 여부 확인해줘'],
          },
        ),
      ];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: AgentChatFullPanel(controller: controller)),
      ),
    );
    await tester.pump();

    expect(find.textContaining('삼성전자'), findsWidgets);
    expect(find.text('삼성전자 현재가'), findsOneWidget);
    expect(find.text('005930 · KIS'), findsOneWidget);
    expect(find.text('₩72,000'), findsOneWidget);
    expect(find.text('NO ORDER'), findsWidgets);
    expect(find.text('NO VALIDATION'), findsWidgets);
    expect(find.text('이 종목 분석해줘'), findsOneWidget);
    for (final marker in _mojibakeMarkers) {
      expect(find.textContaining(marker), findsNothing);
    }

    controller.dispose();
  });
}

final _mojibakeMarkers = List<String>.unmodifiable(
    [0x00EC, 0x00EB, 0x00EA, 0xFFFD].map(String.fromCharCode));

class _NoopApiClient extends ApiClient {}
