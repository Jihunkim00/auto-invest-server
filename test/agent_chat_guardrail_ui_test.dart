import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_full_panel.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';

void main() {
  testWidgets('blocked Agent Chat live-order answer exposes no live action',
      (tester) async {
    final controller = DashboardController(_NoopApiClient(), autoload: false)
      ..agentChatMode = AgentChatPanelMode.fullscreen
      ..activeAgentConversationKey = 'conv_blocked_pr65'
      ..kisLiveConfirmation = true
      ..latestAgentPlan = null
      ..agentMessages = [
        AgentChatMessage(
          id: 'blocked-answer',
          role: AgentChatRole.assistant,
          text: '채팅에서는 실주문을 직접 제출할 수 없습니다. 주문은 실행하지 않았습니다.',
          createdAt: DateTime.utc(2026, 6, 19),
          status: AgentChatStatus.blocked,
          safetyBadges: const ['BLOCKED', 'SERVER-SIDE API', 'NO AUTO SUBMIT'],
          metadata: const {
            'intent_category': 'live_order_request',
            'answer_type': 'blocked',
            'selected_tools': [
              {'tool_name': 'live_order_request_blocker'},
            ],
            'safety': {
              'real_order_submitted': false,
              'broker_submit_called': false,
              'manual_submit_called': false,
              'validation_called': false,
              'confirm_live_auto_checked': false,
            },
          },
        ),
      ];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: AgentChatFullPanel(controller: controller)),
      ),
    );
    await tester.pump();

    expect(find.textContaining('실주문'), findsOneWidget);
    expect(find.textContaining('주문은 실행하지 않았습니다'), findsOneWidget);
    expect(find.text('BLOCKED'), findsOneWidget);
    expect(find.text('NO AUTO SUBMIT'), findsWidgets);
    expect(find.text('Submit Live Order'), findsNothing);
    expect(find.text('CONFIRM_LIVE MANUAL'), findsNothing);
    expect(find.byKey(const ValueKey('agent-prepare-manual-ticket')),
        findsNothing);
    expect(find.byKey(const ValueKey('agent-run-safe-action')), findsNothing);

    controller.dispose();
  });
}

class _NoopApiClient extends ApiClient {}
