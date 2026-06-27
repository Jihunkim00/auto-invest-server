import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_full_panel.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';
import 'package:auto_invest_dashboard/models/agent_plan.dart';

void main() {
  testWidgets('read-only answer displays bubble and badges without plan card',
      (tester) async {
    final controller = DashboardController(
      _NoopApiClient(),
      autoload: false,
      initialLanguage: AppLanguage.english,
    )
      ..agentChatMode = AgentChatPanelMode.fullscreen
      ..activeAgentConversationKey = 'conv_readonly'
      ..latestAgentPlan = null
      ..agentMessages = [
        AgentChatMessage(
          id: 'answer',
          role: AgentChatRole.assistant,
          text: '삼성전자는 005930으로 조회됩니다. 현재가는 ₩72,000입니다.',
          createdAt: DateTime.utc(2026, 6, 18),
          status: AgentChatStatus.sent,
          safetyBadges: const ['READ ONLY', 'KIS', 'NO AUTO SUBMIT'],
        ),
      ];

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: AgentChatFullPanel(controller: controller)),
    ));

    expect(find.textContaining('현재가는'), findsOneWidget);
    expect(find.text('READ ONLY'), findsOneWidget);
    expect(find.text('NO AUTO SUBMIT'), findsWidgets);
    expect(find.byKey(const ValueKey('agent-prepare-manual-ticket')),
        findsNothing);
    expect(find.byKey(const ValueKey('agent-run-safe-action')), findsNothing);

    controller.dispose();
  });

  testWidgets('manual ticket answer shows prepare button only', (tester) async {
    final controller = DashboardController(
      _NoopApiClient(),
      autoload: false,
      initialLanguage: AppLanguage.english,
    )
      ..agentChatMode = AgentChatPanelMode.fullscreen
      ..activeAgentConversationKey = 'conv_manual'
      ..latestAgentPlan = _manualPlan()
      ..agentMessages = [
        AgentChatMessage(
          id: 'answer',
          role: AgentChatRole.assistant,
          text: '수동 주문 티켓 검토 계획을 준비했습니다. 주문은 실행하지 않았습니다.',
          createdAt: DateTime.utc(2026, 6, 18),
          status: AgentChatStatus.readyForReview,
          planId: 89,
          prefillAvailable: true,
          safetyBadges: const [
            'PREFILL ONLY',
            'MANUAL VALIDATION REQUIRED',
            'NO AUTO SUBMIT',
          ],
        ),
      ];

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: AgentChatFullPanel(controller: controller)),
    ));

    expect(find.text('Prepare Manual Ticket'), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-prepare-manual-ticket')),
        findsOneWidget);
    expect(find.text('Submit Live Order'), findsNothing);
    expect(find.byKey(const ValueKey('agent-run-safe-action')), findsNothing);

    controller.dispose();
  });

  testWidgets('blocked live-order answer does not expose submit action',
      (tester) async {
    final controller = DashboardController(
      _NoopApiClient(),
      autoload: false,
      initialLanguage: AppLanguage.english,
    )
      ..agentChatMode = AgentChatPanelMode.fullscreen
      ..activeAgentConversationKey = 'conv_blocked'
      ..latestAgentPlan = null
      ..agentMessages = [
        AgentChatMessage(
          id: 'answer',
          role: AgentChatRole.assistant,
          text: '채팅에서는 실주문을 직접 제출할 수 없습니다.',
          createdAt: DateTime.utc(2026, 6, 18),
          status: AgentChatStatus.blocked,
          safetyBadges: const ['BLOCKED', 'NO AUTO SUBMIT'],
        ),
      ];

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: AgentChatFullPanel(controller: controller)),
    ));

    expect(find.textContaining('실주문'), findsOneWidget);
    expect(find.text('Submit Live Order'), findsNothing);
    expect(find.byKey(const ValueKey('agent-prepare-manual-ticket')),
        findsNothing);

    controller.dispose();
  });
}

class _NoopApiClient extends ApiClient {}

AgentPlan _manualPlan() {
  return AgentPlan.fromJson({
    'id': 89,
    'plan_key': 'plan_manual',
    'command_type': 'PREPARE_MANUAL_BUY_TICKET',
    'domain': 'order',
    'intent': 'prepare_manual_buy_ticket',
    'market': 'KR',
    'provider': 'kis',
    'symbol': '005930',
    'side': 'buy',
    'risk_level': 'prefill_only',
    'status': 'ready_for_review',
    'plan_title': 'Prepare manual ticket',
    'plan_summary': 'Prepare ticket only.',
    'user_visible_summary': 'Manual ticket only.',
    'command': {
      'budget': {'amount': 30000, 'currency': 'KRW'}
    },
    'execution_policy': {'allow_live_order': false},
    'safety': {'real_order_submitted': false},
    'requires_auth': false,
    'requires_recent_validation': false,
    'requires_confirm_live': false,
    'allow_live_order': false,
    'allow_setting_change': false,
    'allow_scheduler_change': false,
  });
}
