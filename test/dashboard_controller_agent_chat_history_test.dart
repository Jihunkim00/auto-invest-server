import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/agent_chat_conversation.dart';
import 'package:auto_invest_dashboard/models/agent_chat_message.dart';
import 'package:auto_invest_dashboard/models/agent_chat_send_response.dart';
import 'package:auto_invest_dashboard/models/agent_command.dart';
import 'package:auto_invest_dashboard/models/agent_plan.dart';

void main() {
  test('restoreLatestAgentConversation loads persisted active thread',
      () async {
    final api = _AgentChatHistoryFakeApi(
      conversations: [_conversation('agent_conv_latest')],
      messages: [
        _message('stored-user', AgentChatRole.user, 'Show Samsung positions'),
        _message(
          'stored-agent',
          AgentChatRole.assistant,
          'Persisted plan review.',
          messageType: 'plan_review',
        ),
      ],
    );
    final controller = DashboardController(api, autoload: false);

    final result = await controller.restoreLatestAgentConversation();

    expect(result.success, isTrue);
    expect(controller.activeAgentConversationKey, 'agent_conv_latest');
    expect(api.fetchConversationsCalls, 1);
    expect(api.fetchMessagesCalls, 1);
    expect(
        controller.agentMessages.map((message) => message.text),
        containsAll([
          'Show Samsung positions',
          'Persisted plan review.',
        ]));
    expect(controller.agentHistoryError, isNull);

    controller.dispose();
  });

  test('sendAgentMessage restores before chat send and lets backend persist',
      () async {
    final api = _AgentChatHistoryFakeApi(
      conversations: [_conversation('agent_conv_latest')],
      messages: [
        _message('stored-agent', AgentChatRole.assistant, 'Previous summary.'),
      ],
    );
    final controller = DashboardController(api, autoload: false);

    final result = await controller.sendAgentMessage('show my positions');

    expect(result.success, isTrue);
    expect(api.chatSendCalls, 1);
    expect(api.chatConversationKey, 'agent_conv_latest');
    expect(api.chatContext?['conversation_key'], 'agent_conv_latest');
    expect(api.parseCalls, 0);
    expect(api.createPlanCalls, 0);
    expect(api.appendedMessages, isEmpty);
    expect(controller.latestAgentPlan, isNull);
    expect(
      controller.agentMessages.map((message) => message.text),
      contains('Previous summary.'),
    );
    expect(
      controller.agentMessages.map((message) => message.text),
      contains('Read-only positions summary.'),
    );

    controller.dispose();
  });

  test('chat send failure falls back and append failure keeps local plan',
      () async {
    final api = _AgentChatHistoryFakeApi(
      throwAppend: true,
      throwChatSend: true,
    );
    final controller = DashboardController(api, autoload: false);

    final result = await controller.sendAgentMessage('show my positions');

    expect(result.success, isTrue);
    expect(api.createConversationCalls, 1);
    expect(api.parseCalls, 1);
    expect(api.createPlanCalls, 1);
    expect(api.appendCalls, 2);
    expect(controller.activeAgentConversationKey, 'agent_conv_created_1');
    expect(controller.agentHistoryError, contains('Saved locally only'));
    expect(
      controller.agentMessages
          .any((message) => message.text == 'show my positions'),
      isTrue,
    );
    expect(controller.latestAgentPlan?.id, 88);

    controller.dispose();
  });

  test('new and archive conversation controls reset visible thread', () async {
    final api = _AgentChatHistoryFakeApi(
      conversations: [_conversation('agent_conv_old')],
      messages: [_message('old', AgentChatRole.user, 'Old chat')],
    );
    final controller = DashboardController(api, autoload: false);

    final startResult = await controller.startNewAgentConversation();

    expect(startResult.success, isTrue);
    expect(controller.activeAgentConversationKey, 'agent_conv_created_1');
    expect(controller.agentMessages.single.role, AgentChatRole.safety);

    final archiveResult = await controller.archiveAgentConversation();

    expect(archiveResult.success, isTrue);
    expect(api.archiveCalls, 1);
    expect(api.archivedKeys, contains('agent_conv_created_1'));
    expect(controller.activeAgentConversationKey, isNull);
    expect(controller.agentMessages.single.role, AgentChatRole.safety);

    controller.dispose();
  });
}

class _AgentChatHistoryFakeApi extends ApiClient {
  _AgentChatHistoryFakeApi({
    List<AgentChatConversation>? conversations,
    List<AgentChatMessage>? messages,
    this.throwAppend = false,
    this.throwChatSend = false,
  })  : conversations =
            List<AgentChatConversation>.of(conversations ?? const []),
        messages = List<AgentChatMessage>.of(messages ?? const []);

  final List<AgentChatConversation> conversations;
  final List<AgentChatMessage> messages;
  final bool throwAppend;
  final bool throwChatSend;
  final List<AgentChatMessage> appendedMessages = [];
  final List<String> archivedKeys = [];

  int fetchConversationsCalls = 0;
  int createConversationCalls = 0;
  int fetchMessagesCalls = 0;
  int chatSendCalls = 0;
  int appendCalls = 0;
  int parseCalls = 0;
  int createPlanCalls = 0;
  int archiveCalls = 0;
  String? chatConversationKey;
  Map<String, dynamic>? chatContext;
  String? parseConversationId;
  Map<String, dynamic>? parseContext;

  @override
  Future<List<AgentChatConversation>> fetchAgentChatConversations({
    String status = 'active',
    int limit = 20,
  }) async {
    fetchConversationsCalls += 1;
    return conversations
        .where((conversation) => conversation.status == status)
        .take(limit)
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
      id: 100 + createConversationCalls,
      title: title,
      source: source,
      metadata: metadata ?? const {},
    );
    conversations.insert(0, conversation);
    return conversation;
  }

  @override
  Future<List<AgentChatMessage>> fetchAgentChatMessages(
    String conversationKey, {
    int limit = 100,
    int? beforeId,
  }) async {
    fetchMessagesCalls += 1;
    return messages
        .where((message) =>
            message.conversationKey == null ||
            message.conversationKey == conversationKey)
        .take(limit)
        .toList();
  }

  @override
  Future<AgentChatSendResponse> sendAgentChatMessage({
    required String message,
    String? conversationKey,
    Map<String, dynamic>? context,
    bool autoCreateConversation = true,
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    chatSendCalls += 1;
    chatConversationKey = conversationKey;
    chatContext = context;
    if (throwChatSend) {
      throw const ApiRequestException('chat send failed');
    }
    return AgentChatSendResponse.fromJson({
      'conversation_key': conversationKey ?? 'agent_conv_created_1',
      'user_message_id': 10,
      'assistant_message_id': 11,
      'intent': {
        'category': 'read_only_positions_query',
        'supported': true,
        'confidence': 0.9,
        'market': 'KR',
        'provider': 'kis',
        'side': 'none',
        'requires_plan': false,
        'requires_auth': false,
        'requires_manual_confirmation': false,
        'fallback_used': true,
        'parser_status': 'fallback',
      },
      'answer': {
        'role': 'assistant',
        'text': 'Read-only positions summary.',
        'answer_type': 'read_only_result',
      },
      'data': {'positions': [], 'count': 0},
      'available_actions': [],
      'safety': {
        'read_only': true,
        'safe_execution_only': true,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'validation_called': false,
        'setting_changed': false,
        'scheduler_changed': false,
        'confirm_live_auto_checked': false,
      },
    });
  }

  @override
  Future<AgentChatMessage> appendAgentChatMessage({
    required String conversationKey,
    required String role,
    required String text,
    String messageType = 'plain_text',
    String status = 'completed',
    int? commandLogId,
    int? planId,
    int? planRunId,
    int? authApprovalRequestId,
    int? prefillSourcePlanId,
    String? modelName,
    String? parserStatus,
    Map<String, dynamic>? safety,
    Map<String, dynamic>? metadata,
  }) async {
    appendCalls += 1;
    if (throwAppend) {
      throw const ApiRequestException('history sync failed');
    }
    final message = AgentChatMessage(
      id: 'persisted-$appendCalls',
      role: agentChatRoleFromString(role),
      text: text,
      createdAt: DateTime.utc(2026, 6, 18, 9, appendCalls),
      status: agentChatStatusFromString(status),
      conversationKey: conversationKey,
      messageType: messageType,
      commandLogId: commandLogId,
      planId: planId,
      runId: planRunId,
      modelName: modelName,
      parserStatus: parserStatus,
      metadata: metadata ?? const {},
    );
    appendedMessages.add(message);
    messages.add(message);
    return message;
  }

  @override
  Future<AgentChatConversation> archiveAgentChatConversation(
    String conversationKey,
  ) async {
    archiveCalls += 1;
    archivedKeys.add(conversationKey);
    return _conversation(conversationKey, status: 'archived');
  }

  @override
  Future<AgentCommandParseResult> parseAgentCommand({
    required String message,
    String? conversationId,
    Map<String, dynamic>? context,
  }) async {
    parseCalls += 1;
    parseConversationId = conversationId;
    parseContext = context;
    return AgentCommandParseResult.fromJson({
      'status': 'parsed',
      'parser_status': 'gpt',
      'model_name': 'gpt-5.4-mini',
      'command_log_id': 77,
      'command': {
        'schema_version': 'autoinvest_command_v1',
        'command_type': 'SHOW_POSITIONS',
        'domain': 'position',
        'intent': 'show_positions',
        'market': 'KR',
        'provider': 'kis',
        'side': 'none',
        'risk_level': 'read_only',
        'requires_auth': false,
        'user_visible_summary': 'Command parsed.',
        'execution_policy': {'allow_live_order': false},
        'safety': {'real_order_submitted': false},
      },
      'safety': {'real_order_submitted': false},
    });
  }

  @override
  Future<AgentPlanCreateResult> createAgentPlanFromCommand(
    int commandLogId, {
    String? planTitle,
    int expiresInMinutes = 60,
  }) async {
    createPlanCalls += 1;
    return AgentPlanCreateResult(
      status: 'plan_created',
      plan: _safePlan(),
      auth: const {'required': false},
      safety: const {'real_order_submitted': false},
    );
  }
}

AgentChatConversation _conversation(
  String key, {
  int id = 1,
  String? title,
  String status = 'active',
  String source = 'flutter_dashboard',
  Map<String, dynamic> metadata = const {},
}) {
  return AgentChatConversation(
    id: id,
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
  String conversationKey = 'agent_conv_latest',
  String messageType = 'plain_text',
}) {
  return AgentChatMessage(
    id: id,
    role: role,
    text: text,
    createdAt: DateTime.utc(2026, 6, 18),
    status: AgentChatStatus.sent,
    conversationKey: conversationKey,
    messageType: messageType,
  );
}

AgentPlan _safePlan() {
  return AgentPlan.fromJson({
    'id': 88,
    'plan_key': 'plan_safe',
    'command_type': 'SHOW_POSITIONS',
    'domain': 'position',
    'intent': 'show_positions',
    'market': 'KR',
    'provider': 'kis',
    'symbol': null,
    'side': 'none',
    'risk_level': 'read_only',
    'status': 'ready',
    'plan_title': 'Show positions',
    'plan_summary': 'Review positions.',
    'user_visible_summary': 'Positions can be reviewed safely.',
    'command': {'command_type': 'SHOW_POSITIONS'},
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
