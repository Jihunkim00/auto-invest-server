import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_full_panel.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';
import 'package:auto_invest_dashboard/models/agent_chat_send_response.dart';

void main() {
  testWidgets(
      'follow-up suggestion chip sends the suggestion through chat send',
      (tester) async {
    final api = _FollowUpFakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..agentChatMode = AgentChatPanelMode.fullscreen
      ..activeAgentConversationKey = 'conv_followup_pr65'
      ..agentMessages = [
        AgentChatMessage(
          id: 'price-answer',
          role: AgentChatRole.assistant,
          text: '삼성전자는 005930로 조회했습니다. 현재가는 KRW 72,000입니다.',
          createdAt: DateTime.utc(2026, 6, 19),
          status: AgentChatStatus.sent,
          safetyBadges: const ['READ ONLY', 'NO AUTO SUBMIT'],
          metadata: const {
            'result_cards': [
              {
                'card_type': 'price',
                'title': '삼성전자 현재가',
                'subtitle': '005930 / KIS',
                'primary_value': 'KRW 72,000',
                'badges': ['READ ONLY', 'NO ORDER'],
                'rows': [],
                'data': {'symbol': '005930'},
              }
            ],
            'follow_up_suggestions': ['이 종목을 간단히 분석해줄까요?'],
          },
        ),
      ];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: AgentChatFullPanel(controller: controller)),
      ),
    );
    await tester.pump();

    expect(find.text('이 종목을 간단히 분석해줄까요?'), findsOneWidget);

    await tester.tap(find.text('이 종목을 간단히 분석해줄까요?'));
    await tester.pumpAndSettle();

    expect(api.sentMessages, ['이 종목을 간단히 분석해줄까요?']);
    expect(api.sentConversationKeys, ['conv_followup_pr65']);
    expect(controller.agentMessages.last.text, contains('안전 분석만 수행했습니다'));
    expect(
        controller.agentMessages.last.safetyBadges, contains('NO AUTO SUBMIT'));
    expect(controller.kisLiveConfirmation, isFalse);

    controller.dispose();
  });
}

class _FollowUpFakeApiClient extends ApiClient {
  final List<String> sentMessages = [];
  final List<String?> sentConversationKeys = [];

  @override
  Future<AgentChatSendResponse> sendAgentChatMessage({
    required String message,
    String? conversationKey,
    Map<String, dynamic>? context,
    bool autoCreateConversation = true,
  }) async {
    sentMessages.add(message);
    sentConversationKeys.add(conversationKey);
    return AgentChatSendResponse.fromJson({
      'conversation_key': conversationKey ?? 'conv_followup_pr65',
      'intent': {
        'category': 'analysis_request',
        'supported': true,
        'confidence': 0.9,
        'market': 'KR',
        'provider': 'kis',
        'symbol': '005930',
        'symbol_name': '삼성전자',
        'side': 'none',
        'requires_plan': true,
        'requires_auth': false,
        'requires_manual_confirmation': false,
        'fallback_used': true,
        'parser_status': 'fallback',
      },
      'answer': {
        'role': 'assistant',
        'text': '005930 안전 분석만 수행했습니다. 주문은 제출하지 않았습니다.',
        'answer_type': 'analysis_summary',
      },
      'data': {
        'analysis': {'symbol': '005930', 'action': 'hold'},
      },
      'available_actions': [],
      'safety': {
        'read_only': false,
        'safe_execution_only': true,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'validation_called': false,
        'setting_changed': false,
        'scheduler_changed': false,
        'confirm_live_auto_checked': false,
        'mutation': false,
      },
      'context_snapshot': {
        'last_symbol': '005930',
        'last_symbol_name': '삼성전자',
        'last_market': 'KR',
        'last_provider': 'kis',
      },
      'selected_tools': [
        {
          'tool_name': 'safe_symbol_analysis',
          'arguments': {'symbol': '005930'},
          'reason': 'User asked for safe analysis.',
        }
      ],
      'tool_results': [],
      'result_cards': [],
      'follow_up_suggestions': [],
      'answer_type': 'analysis_summary',
      'fallback_used': true,
    });
  }
}
