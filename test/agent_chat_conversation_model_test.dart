import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_chat_conversation.dart';

void main() {
  test('AgentChatConversationList parses backend conversation payload', () {
    final list = AgentChatConversationList.fromJson({
      'count': 1,
      'conversations': [
        {
          'id': 4,
          'conversation_key': 'agent_conv_20260618',
          'title': 'Samsung review',
          'status': 'active',
          'source': 'flutter_dashboard',
          'metadata': {'market': 'KR'},
          'created_at': '2026-06-18T09:00:00Z',
          'updated_at': '2026-06-18T09:01:00Z',
          'last_message_at': '2026-06-18T09:02:00Z',
        },
      ],
    });

    expect(list.count, 1);
    expect(list.conversations, hasLength(1));
    expect(list.conversations.first.id, 4);
    expect(list.conversations.first.conversationKey, 'agent_conv_20260618');
    expect(list.conversations.first.title, 'Samsung review');
    expect(list.conversations.first.status, 'active');
    expect(list.conversations.first.source, 'flutter_dashboard');
    expect(list.conversations.first.metadata['market'], 'KR');
    expect(list.conversations.first.lastMessageAt, isNotNull);
  });
}
