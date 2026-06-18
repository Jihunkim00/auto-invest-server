import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_full_panel.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_panel.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';

void main() {
  testWidgets('mini panel renders safe server-side chat controls',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: AgentChatPanel(controller: controller),
      ),
    ));

    expect(find.text('Agent Assistant'), findsOneWidget);
    expect(find.text('GPT-BACKED'), findsOneWidget);
    expect(find.text('SERVER-SIDE API'), findsOneWidget);
    expect(find.text('SAFE MODE'), findsOneWidget);
    expect(find.text('NO AUTO SUBMIT'), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-chat-mini-input')), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-chat-fullscreen')), findsOneWidget);

    controller.dispose();
  });

  testWidgets('full panel renders thread input toolbar and safety notice',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..agentChatMode = AgentChatPanelMode.fullscreen
      ..agentMessages = [
        AgentChatMessage(
          id: 'user-1',
          role: AgentChatRole.user,
          text: 'Show positions',
          createdAt: DateTime(2026, 6, 18),
          status: AgentChatStatus.sent,
        ),
        AgentChatMessage(
          id: 'assistant-1',
          role: AgentChatRole.assistant,
          text: 'Plan is ready for review.',
          createdAt: DateTime(2026, 6, 18),
          status: AgentChatStatus.readyForReview,
        ),
      ];

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: AgentChatFullPanel(controller: controller),
      ),
    ));

    expect(find.byKey(const Key('agent-chat-full-panel')), findsOneWidget);
    expect(find.text('Show positions'), findsOneWidget);
    expect(find.text('Plan is ready for review.'), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-chat-full-input')), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-chat-minimize')), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-chat-full-resize')), findsOneWidget);
    expect(find.textContaining('Agent never submits live orders from chat'),
        findsOneWidget);

    controller.dispose();
  });
}
