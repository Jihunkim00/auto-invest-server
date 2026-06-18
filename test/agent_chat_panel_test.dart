import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_full_panel.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/agent_chat_panel.dart';
import 'package:auto_invest_dashboard/models/agent_chat_conversation.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';

void main() {
  testWidgets('mini panel renders safe server-side chat controls',
      (tester) async {
    final controller =
        DashboardController(_PanelFakeApiClient(), autoload: false);

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
    expect(find.byKey(const ValueKey('agent-chat-new-chat')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('agent-chat-refresh-history')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('agent-chat-fullscreen')), findsOneWidget);

    controller.dispose();
  });

  testWidgets('mini panel restores persisted history on first render',
      (tester) async {
    final api = _PanelFakeApiClient(
      conversations: [_conversation('agent_conv_ui')],
      messages: [
        _message('stored-agent', AgentChatRole.assistant, 'Restored answer.'),
      ],
    );
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: _listeningAgentPanel(controller),
      ),
    ));
    await tester.pump();
    await tester.pump();

    expect(api.fetchConversationsCalls, 1);
    expect(api.fetchMessagesCalls, 1);
    expect(controller.activeAgentConversationKey, 'agent_conv_ui');
    expect(find.text('Restored answer.'), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-chat-new-chat')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('agent-chat-refresh-history')),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('full panel renders thread input toolbar and safety notice',
      (tester) async {
    final controller = DashboardController(_PanelFakeApiClient(), autoload: false)
      ..agentChatMode = AgentChatPanelMode.fullscreen
      ..activeAgentConversationKey = 'agent_conv_active'
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
    expect(
      find.byKey(const ValueKey('agent-chat-full-new-chat')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('agent-chat-full-refresh-history')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('agent-chat-full-archive')), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-chat-minimize')), findsOneWidget);
    expect(find.byKey(const ValueKey('agent-chat-full-resize')), findsOneWidget);
    expect(find.textContaining('Agent never submits live orders from chat'),
        findsOneWidget);

    controller.dispose();
  });
}

Widget _listeningAgentPanel(DashboardController controller) {
  return AnimatedBuilder(
    animation: controller,
    builder: (context, _) => AgentChatPanel(controller: controller),
  );
}

class _PanelFakeApiClient extends ApiClient {
  _PanelFakeApiClient({
    List<AgentChatConversation>? conversations,
    List<AgentChatMessage>? messages,
  })  : conversations = List<AgentChatConversation>.of(conversations ?? const []),
        messages = List<AgentChatMessage>.of(messages ?? const []);

  final List<AgentChatConversation> conversations;
  final List<AgentChatMessage> messages;
  int fetchConversationsCalls = 0;
  int fetchMessagesCalls = 0;
  int createConversationCalls = 0;

  @override
  Future<List<AgentChatConversation>> fetchAgentChatConversations({
    String status = 'active',
    int limit = 20,
  }) async {
    fetchConversationsCalls += 1;
    return conversations.where((item) => item.status == status).toList();
  }

  @override
  Future<List<AgentChatMessage>> fetchAgentChatMessages(
    String conversationKey, {
    int limit = 100,
    int? beforeId,
  }) async {
    fetchMessagesCalls += 1;
    return messages
        .where((item) =>
            item.conversationKey == null ||
            item.conversationKey == conversationKey)
        .toList();
  }

  @override
  Future<AgentChatConversation> createAgentChatConversation({
    String? title,
    String source = 'flutter_dashboard',
    Map<String, dynamic>? metadata,
  }) async {
    createConversationCalls += 1;
    final conversation = _conversation(
      'agent_conv_created_$createConversationCalls',
      title: title,
      source: source,
      metadata: metadata ?? const {},
    );
    conversations.insert(0, conversation);
    return conversation;
  }
}

AgentChatConversation _conversation(
  String key, {
  String? title,
  String status = 'active',
  String source = 'flutter_dashboard',
  Map<String, dynamic> metadata = const {},
}) {
  return AgentChatConversation(
    id: 1,
    conversationKey: key,
    title: title,
    status: status,
    source: source,
    metadata: metadata,
    createdAt: DateTime.utc(2026, 6, 18),
    updatedAt: DateTime.utc(2026, 6, 18, 0, 1),
    lastMessageAt: DateTime.utc(2026, 6, 18, 0, 2),
  );
}

AgentChatMessage _message(
  String id,
  AgentChatRole role,
  String text, {
  String conversationKey = 'agent_conv_ui',
}) {
  return AgentChatMessage(
    id: id,
    role: role,
    text: text,
    createdAt: DateTime.utc(2026, 6, 18),
    status: AgentChatStatus.sent,
    conversationKey: conversationKey,
  );
}
